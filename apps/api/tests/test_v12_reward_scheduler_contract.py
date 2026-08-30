from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
import yaml

from scripts import lead_export_worker, scheduler


def test_scheduler_runs_supplier_rewards_hourly() -> None:
    scheduler_source = Path("scripts/scheduler.py").read_text(encoding="utf-8")
    run_jobs = Path("scripts/run_jobs.py").read_text(encoding="utf-8")
    base_compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    production_overlay = Path("docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "drain_due_supplier_reward_settlement_notified" in scheduler_source
    assert scheduler.HOURLY_JOB_TICKS == 120
    assert "tick % HOURLY_JOB_TICKS == 0" in scheduler_source
    assert '"supplier-rewards"' in run_jobs
    assert "drain_due_supplier_reward_settlement_notified" in run_jobs
    assert '"--max-batches"' in run_jobs

    # Production deployment uses Docker Compose's multi-file overlay model:
    # docker-compose.prod.yml overrides security/image settings while the
    # scheduler command remains defined in docker-compose.yml.
    assert "scheduler:" in base_compose
    assert "scheduler-entrypoint.sh" in base_compose
    scheduler_compose = base_compose.split("  scheduler:", maxsplit=1)[1].split("  nginx:", maxsplit=1)[0]
    assert "healthcheck:" in scheduler_compose
    assert "SCHEDULER_HEARTBEAT_FILE" in scheduler_compose
    assert "SCHEDULER_HEARTBEAT_MAX_AGE_SECONDS" in scheduler_compose
    assert "/proc/1" not in scheduler_compose
    assert "scheduler:" in production_overlay
    assert "init: true" in production_overlay.split("  scheduler:", maxsplit=1)[1]
    assert 'AUTO_CREATE_SCHEMA: "false"' in production_overlay


def test_production_scheduler_heartbeat_survives_compose_overlay() -> None:
    base = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    production = yaml.safe_load(Path("docker-compose.prod.yml").read_text(encoding="utf-8"))
    rendered_scheduler = {
        **base["services"]["scheduler"],
        **production["services"]["scheduler"],
    }
    healthcheck = " ".join(rendered_scheduler["healthcheck"]["test"])
    assert rendered_scheduler["init"] is True
    assert rendered_scheduler["read_only"] is True
    assert "SCHEDULER_HEARTBEAT_FILE" in healthcheck
    assert "/proc/1" not in healthcheck


def test_large_lead_exports_run_in_an_isolated_worker() -> None:
    scheduler_source = Path("scripts/scheduler.py").read_text(encoding="utf-8")
    manual_jobs_source = Path("scripts/run_jobs.py").read_text(encoding="utf-8")
    worker_source = Path("scripts/lead_export_worker.py").read_text(encoding="utf-8")
    worker_entrypoint = Path("docker/lead-export-worker-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    base = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    production = yaml.safe_load(
        Path("docker-compose.prod.yml").read_text(encoding="utf-8")
    )

    assert "process_lead_export_tasks" not in scheduler_source
    assert "process_lead_export_tasks(" in worker_source
    assert "progress=publish_heartbeat" in worker_source
    assert 'if args.job == "lead-exports"' in manual_jobs_source
    assert 'if args.job in {"lead-exports", "all"}' not in manual_jobs_source
    assert "process_lead_export_tasks(db, limit=1)" in manual_jobs_source
    assert "lead-export-worker-entrypoint.sh" in str(
        base["services"]["lead-export-worker"]["entrypoint"]
    )
    assert ". /app/docker/prepare-env.sh" in worker_entrypoint
    assert production["services"]["lead-export-worker"]["read_only"] is True
    worker = base["services"]["lead-export-worker"]
    assert worker["environment"]["SYNC_THREADPOOL_TOKENS"] == (
        "${LEAD_EXPORT_SYNC_THREADPOOL_TOKENS:-2}"
    )
    assert worker["environment"]["MAX_IN_FLIGHT_REQUESTS"] == (
        "${LEAD_EXPORT_MAX_IN_FLIGHT_REQUESTS:-2}"
    )
    for compose_worker in (worker, production["services"]["lead-export-worker"]):
        tmpfs = " ".join(compose_worker["tmpfs"])
        assert "640m" in tmpfs
        assert "mode=0700" in tmpfs
        assert "uid=10001" in tmpfs
        assert "gid=10001" in tmpfs
        assert compose_worker["environment"]["TMPDIR"] == "/tmp"
    assert worker["healthcheck"].get("disable") is not True
    assert "LEAD_EXPORT_HEARTBEAT_FILE" in " ".join(
        worker["healthcheck"]["test"]
    )
    operations = Path("docs/runbooks/OPERATIONS.md").read_text(encoding="utf-8")
    assert "stop lead-export-worker" in operations


def test_lead_export_worker_publishes_heartbeat_atomically(tmp_path: Path) -> None:
    heartbeat = tmp_path / "lead-export-heartbeat"

    lead_export_worker.publish_heartbeat(heartbeat)

    assert heartbeat.is_file()
    assert float(heartbeat.read_text(encoding="ascii")) == pytest.approx(
        heartbeat.stat().st_mtime,
        abs=1.0,
    )
    assert not heartbeat.with_name(f".{heartbeat.name}.tmp").exists()

    lead_export_worker.clear_heartbeat(heartbeat)
    assert not heartbeat.exists()


def test_lead_export_worker_heartbeat_is_safe_for_parallel_upload_callbacks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    heartbeat = tmp_path / "lead-export-heartbeat"
    barrier = Barrier(2)
    original_write_text = Path.write_text

    def synchronized_write(path: Path, *args, **kwargs):
        result = original_write_text(path, *args, **kwargs)
        if path.name.startswith(f".{heartbeat.name}."):
            barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(Path, "write_text", synchronized_write)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(lead_export_worker.publish_heartbeat, heartbeat)
            for _index in range(2)
        ]
        for future in futures:
            future.result(timeout=10)

    assert heartbeat.is_file()
    assert not list(tmp_path.glob(f".{heartbeat.name}.*.tmp"))


def test_lead_export_worker_advances_heartbeat_during_real_task_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeSession()
    heartbeats: list[str] = []
    monkeypatch.setattr(lead_export_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        lead_export_worker,
        "publish_heartbeat",
        lambda: heartbeats.append("progress"),
    )

    def process(_db, *, limit: int, progress) -> dict[str, int]:
        assert _db is db
        assert limit == 1
        progress()
        progress()
        return {"claimed": 1, "completed": 1, "failed": 0, "superseded": 0}

    monkeypatch.setattr(lead_export_worker, "process_lead_export_tasks", process)

    result, succeeded = lead_export_worker.run_once()

    assert succeeded is True
    assert result["completed"] == 1
    assert heartbeats == ["progress", "progress"]
    assert db.committed is True


def test_lead_export_worker_does_not_fake_progress_after_a_task_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeSession()
    heartbeats: list[str] = []
    monkeypatch.setattr(lead_export_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        lead_export_worker,
        "publish_heartbeat",
        lambda: heartbeats.append("progress"),
    )

    def fail(_db, *, limit: int, progress) -> dict[str, int]:
        assert _db is db
        assert limit == 1
        raise RuntimeError("synthetic lead export failure")

    monkeypatch.setattr(lead_export_worker, "process_lead_export_tasks", fail)

    _result, succeeded = lead_export_worker.run_once()

    assert succeeded is False
    assert heartbeats == []
    assert db.rolled_back is True


def test_scheduler_publishes_and_clears_heartbeat_atomically(tmp_path: Path) -> None:
    heartbeat = tmp_path / "scheduler-heartbeat"

    scheduler.publish_heartbeat(heartbeat)

    assert heartbeat.is_file()
    assert float(heartbeat.read_text(encoding="ascii")) == pytest.approx(
        heartbeat.stat().st_mtime,
        abs=1.0,
    )
    assert not heartbeat.with_name(f".{heartbeat.name}.tmp").exists()

    scheduler.clear_heartbeat(heartbeat)
    assert not heartbeat.exists()


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_scheduler_cycle_reports_success_only_after_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeSession()
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    monkeypatch.setattr(scheduler, "process_outbox", lambda *_args, **_kwargs: {"sent": 0, "failed": 0})
    monkeypatch.setattr(
        scheduler,
        "process_storage_cleanup",
        lambda *_args, **_kwargs: {"deleted": 0, "failed": 0},
    )
    assert scheduler.run_cycle(run_slow_jobs=False, run_hourly_jobs=False) is True
    assert db.committed is True
    assert db.rolled_back is False


def test_scheduler_cycle_failure_does_not_advance_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeSession()
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    def fail_outbox(*_args: object, **_kwargs: object) -> dict[str, int]:
        raise RuntimeError("synthetic scheduler failure")

    monkeypatch.setattr(scheduler, "process_outbox", fail_outbox)

    assert scheduler.run_cycle(run_slow_jobs=False, run_hourly_jobs=False) is False
    assert db.committed is False
    assert db.rolled_back is True

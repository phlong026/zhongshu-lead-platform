from pathlib import Path

import pytest
import yaml

from scripts import scheduler


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

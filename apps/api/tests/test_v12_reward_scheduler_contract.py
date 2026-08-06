from pathlib import Path


def test_scheduler_runs_supplier_rewards_hourly() -> None:
    scheduler = Path("scripts/scheduler.py").read_text(encoding="utf-8")
    run_jobs = Path("scripts/run_jobs.py").read_text(encoding="utf-8")
    base_compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    production_overlay = Path("docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "drain_due_supplier_reward_settlement" in scheduler
    assert "tick % 120 == 0" in scheduler
    assert '"supplier-rewards"' in run_jobs
    assert "drain_due_supplier_reward_settlement" in run_jobs
    assert '"--max-batches"' in run_jobs

    # Production deployment uses Docker Compose's multi-file overlay model:
    # docker-compose.prod.yml overrides security/image settings while the
    # scheduler command remains defined in docker-compose.yml.
    assert "scheduler:" in base_compose
    assert "scheduler-entrypoint.sh" in base_compose
    assert "scheduler:" in production_overlay
    assert 'AUTO_CREATE_SCHEMA: "false"' in production_overlay

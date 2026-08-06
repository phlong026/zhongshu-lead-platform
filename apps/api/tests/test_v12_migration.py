from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[3]


def _alembic(database_url: str, *args: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_v12_migration_upgrades_and_downgrades_from_v101(tmp_path: Path) -> None:
    database = tmp_path / "migration.db"
    database_url = f"sqlite:///{database}"
    _alembic(database_url, "upgrade", "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "calendar_days" in tables
    assert "supplier_lead_rewards" in tables
    assert "phone_fingerprint" in {column["name"] for column in inspector.get_columns("leads")}
    assert "appeal_deadline_at" in {column["name"] for column in inspector.get_columns("assignments")}
    assert "rule_snapshot_json" in {
        column["name"] for column in inspector.get_columns("supplier_lead_rewards")
    }
    indexes = {item["name"]: item for item in inspector.get_indexes("assignments")}
    assert indexes["uq_assignments_active_lead_v12"]["unique"] == 1

    _alembic(database_url, "downgrade", "0001_initial")
    inspector = inspect(engine)
    assert "calendar_days" not in set(inspector.get_table_names())
    assert "phone_fingerprint" not in {column["name"] for column in inspector.get_columns("leads")}
    assert "uq_assignments_active_lead_v12" not in {
        item["name"] for item in inspector.get_indexes("assignments")
    }

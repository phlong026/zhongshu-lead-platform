from __future__ import annotations

from datetime import date, datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import uuid

import sqlalchemy as sa
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


def _required_row(table: sa.Table, **overrides) -> dict:
    """Build a valid migration fixture from the reflected historical schema."""

    now = datetime.now(timezone.utc)
    row: dict = {}
    for column in table.columns:
        if column.name in overrides:
            row[column.name] = overrides[column.name]
            continue
        if column.nullable or column.default is not None or column.server_default is not None:
            continue
        if column.primary_key:
            row[column.name] = str(uuid.uuid4())
        elif isinstance(column.type, sa.DateTime):
            row[column.name] = now
        elif isinstance(column.type, sa.Date):
            row[column.name] = date.today()
        elif isinstance(column.type, sa.Boolean):
            row[column.name] = False
        elif isinstance(column.type, (sa.Integer, sa.BigInteger)):
            row[column.name] = 0
        elif isinstance(column.type, sa.JSON):
            row[column.name] = {}
        else:
            row[column.name] = "fixture"
    row.update(overrides)
    return row


def _seed_legacy_reward_before_snapshot_migration(engine) -> str:
    metadata = sa.MetaData()
    metadata.reflect(engine)
    users = metadata.tables["users"]
    companies = metadata.tables["companies"]
    leads = metadata.tables["leads"]
    assignments = metadata.tables["assignments"]
    rewards = metadata.tables["supplier_lead_rewards"]

    user_id = str(uuid.uuid4())
    supplier_id = str(uuid.uuid4())
    receiver_id = str(uuid.uuid4())
    lead_id = str(uuid.uuid4())
    assignment_id = str(uuid.uuid4())
    reward_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    with engine.begin() as connection:
        connection.execute(
            users.insert(),
            _required_row(
                users,
                id=user_id,
                username=f"migration-{user_id[:8]}",
                display_name="迁移测试用户",
                status="ACTIVE",
                session_version=1,
                created_at=now,
                updated_at=now,
            ),
        )
        connection.execute(
            companies.insert(),
            [
                _required_row(
                    companies,
                    id=supplier_id,
                    code=f"MS-{supplier_id[:8]}",
                    name="历史奖励供应商",
                    status="ACTIVE",
                    level_code="V1",
                    created_at=now,
                    updated_at=now,
                ),
                _required_row(
                    companies,
                    id=receiver_id,
                    code=f"MR-{receiver_id[:8]}",
                    name="历史奖励接收方",
                    status="ACTIVE",
                    level_code="V1",
                    created_at=now,
                    updated_at=now,
                ),
            ],
        )
        connection.execute(
            leads.insert(),
            _required_row(
                leads,
                id=lead_id,
                source_type="SUPPLIER_H5",
                source_kind="SUPPLIER_H5",
                submitter_user_id=user_id,
                supplier_company_id=supplier_id,
                customer_name="历史奖励客户",
                phone_encrypted="ciphertext",
                phone_hash="h" * 64,
                phone_fingerprint="f" * 64,
                consent_confirmed=True,
                status="CLAIMED",
                review_status="APPROVED",
                duplicate_status="CLEAR",
                acquisition_cost_cents=0,
                imported_at=now,
                submitted_at=now,
                snapshot_version=1,
                raw_payload={},
                created_at=now,
                updated_at=now,
            ),
        )
        connection.execute(
            assignments.insert(),
            _required_row(
                assignments,
                id=assignment_id,
                lead_id=lead_id,
                company_id=receiver_id,
                receiver_company_id=receiver_id,
                supplier_company_id=supplier_id,
                status="CLAIMED",
                points_price=200,
                claim_points=200,
                price_version=1,
                lead_snapshot={},
                assigned_by=user_id,
                assigned_at=now,
                claimed_at=now,
                idempotency_key=f"migration-assignment-{assignment_id}",
                created_at=now,
                updated_at=now,
            ),
        )
        connection.execute(
            rewards.insert(),
            _required_row(
                rewards,
                id=reward_id,
                lead_id=lead_id,
                assignment_id=assignment_id,
                supplier_company_id=supplier_id,
                receiver_company_id=receiver_id,
                status="OBSERVING",
                claim_points=200,
                reward_ratio_bps=2750,
                reward_points=55,
                rule_version=7,
                created_at=now,
                updated_at=now,
            ),
        )
    return reward_id


def test_v12_migration_upgrades_and_downgrades_from_v101(tmp_path: Path) -> None:
    database = tmp_path / "migration.db"
    database_url = f"sqlite:///{database}"
    _alembic(database_url, "upgrade", "0003_v12_active_assignment")

    engine = create_engine(database_url)
    reward_id = _seed_legacy_reward_before_snapshot_migration(engine)
    _alembic(database_url, "upgrade", "head")

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

    metadata = sa.MetaData()
    metadata.reflect(engine, only=["supplier_lead_rewards"])
    rewards = metadata.tables["supplier_lead_rewards"]
    with engine.connect() as connection:
        snapshot = connection.execute(
            sa.select(rewards.c.rule_snapshot_json).where(rewards.c.id == reward_id)
        ).scalar_one()
    assert snapshot["legacy_backfill"] is True
    assert snapshot["ratio_bps"] == 2750
    assert snapshot["version"] == 7
    assert snapshot["hard_duplicate_days"] == 90
    assert snapshot["reward_duplicate_days"] == 180
    assert snapshot["historical_suspect_days"] == 365

    _alembic(database_url, "downgrade", "0001_initial")
    inspector = inspect(engine)
    assert "calendar_days" not in set(inspector.get_table_names())
    assert "phone_fingerprint" not in {column["name"] for column in inspector.get_columns("leads")}
    assert "uq_assignments_active_lead_v12" not in {
        item["name"] for item in inspector.get_indexes("assignments")
    }

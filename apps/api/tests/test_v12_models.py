from __future__ import annotations

from sqlalchemy import create_engine, inspect

from apps.api.src.core.database import Base
from apps.api.src.core.models import Assignment, Lead, ReturnRequest, VerificationTask
from apps.api.src.core.models_v12 import SupplierLeadReward


def test_v12_metadata_extends_existing_tables_and_creates_foundation_tables() -> None:
    assert {"source_kind", "phone_fingerprint", "review_status"} <= set(Lead.__table__.c.keys())
    assert {"appeal_deadline_at", "reward_due_at"} <= set(Assignment.__table__.c.keys())
    assert {"task_type", "return_request_id"} <= set(VerificationTask.__table__.c.keys())
    assert {"appeal_deadline_at", "verification_task_id"} <= set(ReturnRequest.__table__.c.keys())
    assert SupplierLeadReward.__table__.c.assignment_id.unique is None
    assert any(
        constraint.name == "uq_supplier_reward_assignment"
        for constraint in SupplierLeadReward.__table__.constraints
    )


def test_v12_metadata_can_create_sqlite_schema() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    assert {
        "calendar_days",
        "company_lead_capabilities",
        "company_service_areas_v12",
        "lead_dedup_events",
        "dedup_overrides",
        "supplier_lead_rewards",
        "v12_migration_checkpoints",
    } <= tables

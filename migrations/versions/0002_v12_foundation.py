"""V1.2 domain foundation.

Revision ID: 0002_v12_foundation
Revises: 0001_initial
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_v12_foundation"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _columns(table_name: str) -> set[str]:
    return {item["name"] for item in _inspector().get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {item["name"] for item in _inspector().get_indexes(table_name) if item.get("name")}


def _add_columns(table_name: str, columns: list[sa.Column]) -> None:
    existing = _columns(table_name)
    pending = [column for column in columns if column.name not in existing]
    if not pending:
        return
    with op.batch_alter_table(table_name) as batch:
        for column in pending:
            batch.add_column(column)


def _create_index(name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if name not in _indexes(table_name):
        op.create_index(name, table_name, columns, unique=unique)


def _drop_index(name: str, table_name: str) -> None:
    if _has_table(table_name) and name in _indexes(table_name):
        op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    _add_columns(
        "leads",
        [
            sa.Column("source_kind", sa.String(32), nullable=True),
            sa.Column("submitter_user_id", sa.String(36), sa.ForeignKey("users.id", name="fk_leads_submitter_user_v12", ondelete="SET NULL"), nullable=True),
            sa.Column("supplier_company_id", sa.String(36), sa.ForeignKey("companies.id", name="fk_leads_supplier_company_v12", ondelete="SET NULL"), nullable=True),
            sa.Column("consent_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("phone_fingerprint", sa.String(64), nullable=True),
            sa.Column("duplicate_status", sa.String(32), nullable=True),
            sa.Column("review_status", sa.String(32), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        ],
    )
    _add_columns(
        "assignments",
        [
            sa.Column("claim_points", sa.Integer(), nullable=True),
            sa.Column("appeal_deadline_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reward_due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("supplier_company_id", sa.String(36), sa.ForeignKey("companies.id", name="fk_assignments_supplier_company_v12", ondelete="SET NULL"), nullable=True),
            sa.Column("receiver_company_id", sa.String(36), sa.ForeignKey("companies.id", name="fk_assignments_receiver_company_v12", ondelete="SET NULL"), nullable=True),
        ],
    )
    _add_columns(
        "verification_tasks",
        [
            sa.Column("task_type", sa.String(32), nullable=True),
            sa.Column("return_request_id", sa.String(36), sa.ForeignKey("return_requests.id", name="fk_verification_return_request_v12", ondelete="SET NULL"), nullable=True),
            sa.Column("assignment_id", sa.String(36), sa.ForeignKey("assignments.id", name="fk_verification_assignment_v12", ondelete="SET NULL"), nullable=True),
            sa.Column("contact_result", sa.String(64), nullable=True),
            sa.Column("verification_conclusion", sa.String(64), nullable=True),
        ],
    )
    _add_columns(
        "return_requests",
        [
            sa.Column("appeal_deadline_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verification_task_id", sa.String(36), sa.ForeignKey("verification_tasks.id", name="fk_return_verification_task_v12", ondelete="SET NULL"), nullable=True),
            sa.Column("final_decision_reason", sa.Text(), nullable=True),
        ],
    )

    if not _has_table("calendar_days"):
        op.create_table(
            "calendar_days",
            sa.Column("day", sa.Date(), primary_key=True),
            sa.Column("is_workday", sa.Boolean(), nullable=False),
            sa.Column("holiday_name", sa.String(128), nullable=True),
            sa.Column("source", sa.String(32), nullable=False, server_default="MANUAL"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    _create_index("ix_calendar_days_is_workday", "calendar_days", ["is_workday"])
    _create_index("ix_calendar_days_updated_by", "calendar_days", ["updated_by"])

    if not _has_table("company_lead_capabilities"):
        op.create_table(
            "company_lead_capabilities",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("capability_code", sa.String(32), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("review_status", sa.String(32), nullable=False, server_default="APPROVED"),
            sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("company_id", "capability_code", name="uq_company_lead_capability"),
        )
    _create_index("ix_company_lead_capability_company", "company_lead_capabilities", ["company_id"])
    _create_index("ix_company_lead_capability_code", "company_lead_capabilities", ["capability_code"])
    _create_index("ix_company_lead_capability_review", "company_lead_capabilities", ["review_status"])

    if not _has_table("company_service_areas_v12"):
        op.create_table(
            "company_service_areas_v12",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("region_code", sa.String(32), nullable=False),
            sa.Column("region_level", sa.String(16), nullable=False, server_default="DISTRICT"),
            sa.Column("is_primary_city", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("review_status", sa.String(32), nullable=False, server_default="PENDING"),
            sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("company_id", "region_code", name="uq_company_service_area_v12"),
        )
    _create_index("ix_company_service_area_company", "company_service_areas_v12", ["company_id"])
    _create_index("ix_company_service_area_region_active", "company_service_areas_v12", ["region_code", "active"])
    _create_index("ix_company_service_area_review", "company_service_areas_v12", ["review_status"])

    if not _has_table("lead_dedup_events"):
        op.create_table(
            "lead_dedup_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("phone_fingerprint", sa.String(64), nullable=False),
            sa.Column("checkpoint", sa.String(32), nullable=False),
            sa.Column("decision", sa.String(32), nullable=False),
            sa.Column("matched_lead_id", sa.String(36), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
            sa.Column("matched_assignment_id", sa.String(36), sa.ForeignKey("assignments.id", ondelete="SET NULL"), nullable=True),
            sa.Column("window_days", sa.Integer(), nullable=True),
            sa.Column("details_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    _create_index("ix_lead_dedup_lead", "lead_dedup_events", ["lead_id"])
    _create_index("ix_lead_dedup_fingerprint_created", "lead_dedup_events", ["phone_fingerprint", "created_at"])
    _create_index("ix_lead_dedup_checkpoint", "lead_dedup_events", ["checkpoint"])
    _create_index("ix_lead_dedup_decision", "lead_dedup_events", ["decision"])
    _create_index("ix_lead_dedup_matched_lead", "lead_dedup_events", ["matched_lead_id"])
    _create_index("ix_lead_dedup_matched_assignment", "lead_dedup_events", ["matched_assignment_id"])

    if not _has_table("dedup_overrides"):
        op.create_table(
            "dedup_overrides",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("dedup_event_id", sa.String(36), sa.ForeignKey("lead_dedup_events.id", ondelete="SET NULL"), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("approved_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    _create_index("ix_dedup_override_lead", "dedup_overrides", ["lead_id"])
    _create_index("ix_dedup_override_event", "dedup_overrides", ["dedup_event_id"])
    _create_index("ix_dedup_override_approved_by", "dedup_overrides", ["approved_by"])

    if not _has_table("supplier_lead_rewards"):
        op.create_table(
            "supplier_lead_rewards",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("assignment_id", sa.String(36), sa.ForeignKey("assignments.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("supplier_company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("receiver_company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="WAITING_CLAIM"),
            sa.Column("claim_points", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reward_ratio_bps", sa.Integer(), nullable=False, server_default="3000"),
            sa.Column("reward_points", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rule_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("appeal_deadline_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reward_due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ledger_id", sa.String(36), sa.ForeignKey("points_ledgers.id", ondelete="SET NULL"), nullable=True),
            sa.Column("reversal_ledger_id", sa.String(36), sa.ForeignKey("points_ledgers.id", ondelete="SET NULL"), nullable=True),
            sa.Column("exception_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("assignment_id", name="uq_supplier_reward_assignment"),
            sa.CheckConstraint("reward_points >= 0", name="ck_supplier_reward_nonnegative"),
        )
    _create_index("ix_supplier_reward_lead", "supplier_lead_rewards", ["lead_id"])
    _create_index("ix_supplier_reward_supplier", "supplier_lead_rewards", ["supplier_company_id"])
    _create_index("ix_supplier_reward_receiver", "supplier_lead_rewards", ["receiver_company_id"])
    _create_index("ix_supplier_reward_status_due", "supplier_lead_rewards", ["status", "reward_due_at"])
    _create_index("ix_supplier_reward_appeal_deadline", "supplier_lead_rewards", ["appeal_deadline_at"])

    if not _has_table("v12_migration_checkpoints"):
        op.create_table(
            "v12_migration_checkpoints",
            sa.Column("key", sa.String(128), primary_key=True),
            sa.Column("cursor", sa.String(255), nullable=True),
            sa.Column("processed_count", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("error_count", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    _create_index("ix_v12_migration_status", "v12_migration_checkpoints", ["status"])

    for name, table, columns in [
        ("ix_leads_source_kind", "leads", ["source_kind"]),
        ("ix_leads_submitter_user_id", "leads", ["submitter_user_id"]),
        ("ix_leads_supplier_company_id", "leads", ["supplier_company_id"]),
        ("ix_leads_phone_fingerprint", "leads", ["phone_fingerprint"]),
        ("ix_leads_duplicate_status", "leads", ["duplicate_status"]),
        ("ix_leads_review_status", "leads", ["review_status"]),
        ("ix_assignments_appeal_deadline_at", "assignments", ["appeal_deadline_at"]),
        ("ix_assignments_reward_due_at", "assignments", ["reward_due_at"]),
        ("ix_assignments_supplier_company_id", "assignments", ["supplier_company_id"]),
        ("ix_assignments_receiver_company_id", "assignments", ["receiver_company_id"]),
        ("ix_verification_tasks_task_type", "verification_tasks", ["task_type"]),
        ("ix_verification_tasks_return_request_id", "verification_tasks", ["return_request_id"]),
        ("ix_verification_tasks_assignment_id", "verification_tasks", ["assignment_id"]),
        ("ix_return_requests_appeal_deadline_at", "return_requests", ["appeal_deadline_at"]),
        ("ix_return_requests_verification_task_id", "return_requests", ["verification_task_id"]),
    ]:
        _create_index(name, table, columns)


def downgrade() -> None:
    for name, table in [
        ("ix_return_requests_verification_task_id", "return_requests"),
        ("ix_return_requests_appeal_deadline_at", "return_requests"),
        ("ix_verification_tasks_assignment_id", "verification_tasks"),
        ("ix_verification_tasks_return_request_id", "verification_tasks"),
        ("ix_verification_tasks_task_type", "verification_tasks"),
        ("ix_assignments_receiver_company_id", "assignments"),
        ("ix_assignments_supplier_company_id", "assignments"),
        ("ix_assignments_reward_due_at", "assignments"),
        ("ix_assignments_appeal_deadline_at", "assignments"),
        ("ix_leads_review_status", "leads"),
        ("ix_leads_duplicate_status", "leads"),
        ("ix_leads_phone_fingerprint", "leads"),
        ("ix_leads_supplier_company_id", "leads"),
        ("ix_leads_submitter_user_id", "leads"),
        ("ix_leads_source_kind", "leads"),
    ]:
        _drop_index(name, table)

    for table_name in [
        "v12_migration_checkpoints",
        "supplier_lead_rewards",
        "dedup_overrides",
        "lead_dedup_events",
        "company_service_areas_v12",
        "company_lead_capabilities",
        "calendar_days",
    ]:
        if _has_table(table_name):
            op.drop_table(table_name)

    if _has_table("return_requests"):
        existing = _columns("return_requests")
        with op.batch_alter_table("return_requests") as batch:
            for name in ["final_decision_reason", "verification_task_id", "appeal_deadline_at"]:
                if name in existing:
                    batch.drop_column(name)
    if _has_table("verification_tasks"):
        existing = _columns("verification_tasks")
        with op.batch_alter_table("verification_tasks") as batch:
            for name in ["verification_conclusion", "contact_result", "assignment_id", "return_request_id", "task_type"]:
                if name in existing:
                    batch.drop_column(name)
    if _has_table("assignments"):
        existing = _columns("assignments")
        with op.batch_alter_table("assignments") as batch:
            for name in ["receiver_company_id", "supplier_company_id", "reward_due_at", "appeal_deadline_at", "claim_points"]:
                if name in existing:
                    batch.drop_column(name)
    if _has_table("leads"):
        existing = _columns("leads")
        with op.batch_alter_table("leads") as batch:
            for name in [
                "reviewed_at",
                "submitted_at",
                "review_note",
                "review_status",
                "duplicate_status",
                "phone_fingerprint",
                "consent_confirmed",
                "supplier_company_id",
                "submitter_user_id",
                "source_kind",
            ]:
                if name in existing:
                    batch.drop_column(name)

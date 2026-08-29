"""Add fields and durable records required by the 2026-08-29 feedback batch.

Revision ID: 0015_customer_feedback_829
Revises: 0014_storage_cleanup
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0015_customer_feedback_829"
down_revision = "0014_storage_cleanup"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "source_detail" not in _columns("leads"):
        op.add_column(
            "leads",
            sa.Column("source_detail", sa.String(length=128), nullable=True),
        )
    if "lead_export_tasks" not in _tables():
        op.create_table(
            "lead_export_tasks",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("requested_by", sa.String(length=36), nullable=True),
            sa.Column("requested_by_name", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("attempt_token", sa.String(length=64), nullable=True),
            sa.Column("filters_json", sa.JSON(), nullable=False),
            sa.Column("include_full_phone", sa.Boolean(), nullable=False),
            sa.Column("idempotency_key", sa.String(length=64), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("object_key", sa.String(length=512), nullable=True),
            sa.Column("file_name", sa.String(length=255), nullable=True),
            sa.Column("mime_type", sa.String(length=128), nullable=True),
            sa.Column("file_size", sa.BigInteger(), nullable=True),
            sa.Column("sha256", sa.String(length=64), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["requested_by"],
                ["users.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key", name="uq_lead_export_idempotency"),
        )
        op.create_index(
            "ix_lead_export_status_created",
            "lead_export_tasks",
            ["status", "created_at"],
        )
        op.create_index(
            "ix_lead_export_requester_created",
            "lead_export_tasks",
            ["requested_by", "created_at"],
        )
        op.create_index(
            "ix_lead_export_tasks_requested_by",
            "lead_export_tasks",
            ["requested_by"],
        )
        op.create_index(
            "ix_lead_export_tasks_status",
            "lead_export_tasks",
            ["status"],
        )
        op.create_index(
            "ix_lead_export_tasks_expires_at",
            "lead_export_tasks",
            ["expires_at"],
        )


def downgrade() -> None:
    if "lead_export_tasks" in _tables():
        remaining_exports = op.get_bind().execute(
            sa.text("SELECT COUNT(*) FROM lead_export_tasks")
        ).scalar_one()
        if remaining_exports:
            raise RuntimeError(
                "lead export tasks exist; remove exported objects and task records before downgrade"
            )
    if "source_detail" in _columns("leads"):
        remaining_source_details = op.get_bind().execute(
            sa.text(
                "SELECT COUNT(*) FROM leads "
                "WHERE source_detail IS NOT NULL AND TRIM(source_detail) <> ''"
            )
        ).scalar_one()
        if remaining_source_details:
            raise RuntimeError(
                "lead source details exist; migrate or clear them before downgrade"
            )
    if "lead_export_tasks" in _tables():
        op.drop_table("lead_export_tasks")
    if "source_detail" in _columns("leads"):
        op.drop_column("leads", "source_detail")

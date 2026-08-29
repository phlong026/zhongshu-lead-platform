"""Add a durable outbox for private object deletion.

Revision ID: 0014_storage_cleanup
Revises: 0013_internal_user_test
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0014_storage_cleanup"
down_revision = "0013_internal_user_test"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "storage_cleanup_outbox" in _tables():
        return
    op.create_table(
        "storage_cleanup_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_key", sa.String(length=128), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("storage_backend", sa.String(length=32), nullable=False),
        sa.Column("storage_namespace", sa.String(length=512), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", name="uq_storage_cleanup_event_key"),
    )
    op.create_index(
        "ix_storage_cleanup_outbox_source_id",
        "storage_cleanup_outbox",
        ["source_id"],
    )
    op.create_index(
        "ix_storage_cleanup_outbox_status",
        "storage_cleanup_outbox",
        ["status"],
    )
    op.create_index(
        "ix_storage_cleanup_outbox_next_attempt_at",
        "storage_cleanup_outbox",
        ["next_attempt_at"],
    )


def downgrade() -> None:
    if "storage_cleanup_outbox" in _tables():
        unfinished = op.get_bind().execute(
            sa.text(
                "SELECT COUNT(*) FROM storage_cleanup_outbox "
                "WHERE status <> 'DELETED'"
            )
        ).scalar_one()
        if int(unfinished or 0) > 0:
            raise RuntimeError(
                "unfinished storage cleanup jobs exist; drain or resolve them before downgrade"
            )
        op.drop_index(
            "ix_storage_cleanup_outbox_next_attempt_at",
            table_name="storage_cleanup_outbox",
        )
        op.drop_index(
            "ix_storage_cleanup_outbox_status",
            table_name="storage_cleanup_outbox",
        )
        op.drop_index(
            "ix_storage_cleanup_outbox_source_id",
            table_name="storage_cleanup_outbox",
        )
        op.drop_table("storage_cleanup_outbox")

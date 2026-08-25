"""Add company-internal assignment ownership without changing platform dispatch.

Revision ID: 0010_assignment_internal
Revises: 0009_single_business_role
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0010_assignment_internal"
down_revision = "0009_single_business_role"
branch_labels = None
depends_on = None

_INDEX = "ix_assignment_internal_assignee_status"
_SINGLE_COLUMN_INDEX = "ix_assignments_internal_assignee_user_id"


def _columns() -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns("assignments")}


def _indexes() -> set[str]:
    return {
        str(item["name"])
        for item in sa.inspect(op.get_bind()).get_indexes("assignments")
        if item.get("name")
    }


def upgrade() -> None:
    existing = _columns()
    with op.batch_alter_table("assignments") as batch:
        if "internal_assignee_user_id" not in existing:
            batch.add_column(
                sa.Column(
                    "internal_assignee_user_id",
                    sa.String(36),
                    sa.ForeignKey(
                        "users.id",
                        name="fk_assignments_internal_assignee_user",
                        ondelete="SET NULL",
                    ),
                    nullable=True,
                )
            )
        if "internal_assigned_by" not in existing:
            batch.add_column(
                sa.Column(
                    "internal_assigned_by",
                    sa.String(36),
                    sa.ForeignKey(
                        "users.id",
                        name="fk_assignments_internal_assigned_by_user",
                        ondelete="SET NULL",
                    ),
                    nullable=True,
                )
            )
        if "internal_assigned_at" not in existing:
            batch.add_column(sa.Column("internal_assigned_at", sa.DateTime(timezone=True), nullable=True))
    if _INDEX not in _indexes():
        op.create_index(_INDEX, "assignments", ["internal_assignee_user_id", "status"])


def downgrade() -> None:
    indexes = _indexes()
    for index_name in (_INDEX, _SINGLE_COLUMN_INDEX):
        if index_name in indexes:
            op.drop_index(index_name, table_name="assignments")
    existing = _columns()
    removable = [
        name
        for name in ("internal_assigned_at", "internal_assigned_by", "internal_assignee_user_id")
        if name in existing
    ]
    if removable:
        with op.batch_alter_table("assignments") as batch:
            for name in removable:
                batch.drop_column(name)

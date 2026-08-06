"""Enforce one active assignment per lead.

Revision ID: 0003_v12_active_assignment
Revises: 0002_v12_foundation
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_v12_active_assignment"
down_revision = "0002_v12_foundation"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_assignments_active_lead_v12"
ACTIVE_STATUSES = ("PENDING_CLAIM", "CLAIMED", "FOLLOWING", "RETURN_PENDING")
PREDICATE = "status IN ('PENDING_CLAIM','CLAIMED','FOLLOWING','RETURN_PENDING')"


def _index_names() -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_indexes("assignments")
        if item.get("name")
    }


def upgrade() -> None:
    if INDEX_NAME in _index_names():
        return
    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text(
            "SELECT lead_id, COUNT(*) AS active_count "
            "FROM assignments "
            "WHERE status IN ('PENDING_CLAIM','CLAIMED','FOLLOWING','RETURN_PENDING') "
            "GROUP BY lead_id HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate:
        raise RuntimeError(
            "cannot create active-assignment constraint: "
            f"lead {duplicate.lead_id} has {duplicate.active_count} active assignments"
        )
    predicate = sa.text(PREDICATE)
    op.create_index(
        INDEX_NAME,
        "assignments",
        ["lead_id"],
        unique=True,
        sqlite_where=predicate,
        postgresql_where=predicate,
    )


def downgrade() -> None:
    if INDEX_NAME in _index_names():
        op.drop_index(INDEX_NAME, table_name="assignments")

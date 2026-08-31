"""Add the explicit test-data marker for individual leads.

Revision ID: 0016_lead_test_flag
Revises: 0015_customer_feedback_829
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0016_lead_test_flag"
down_revision = "0015_customer_feedback_829"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("leads")
    }


def upgrade() -> None:
    if "is_test" in _columns():
        return
    op.add_column(
        "leads",
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_leads_is_test", "leads", ["is_test"])


def downgrade() -> None:
    if "is_test" not in _columns():
        return
    op.drop_index("ix_leads_is_test", table_name="leads")
    op.drop_column("leads", "is_test")

"""Persist review notes for company lead capabilities.

Revision ID: 0006_capability_review_note
Revises: 0005_auth_login_hardening
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_capability_review_note"
down_revision = "0005_auth_login_hardening"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_columns("company_lead_capabilities")
    }


def upgrade() -> None:
    if "review_note" in _columns():
        return
    with op.batch_alter_table("company_lead_capabilities") as batch:
        batch.add_column(sa.Column("review_note", sa.Text(), nullable=True))


def downgrade() -> None:
    if "review_note" not in _columns():
        return
    with op.batch_alter_table("company_lead_capabilities") as batch:
        batch.drop_column("review_note")

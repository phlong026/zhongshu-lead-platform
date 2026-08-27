"""Add a test-data marker to franchise companies.

Revision ID: 0012_company_test_flag
Revises: 0011_company_account_req
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0012_company_test_flag"
down_revision = "0011_company_account_req"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("companies")}


def upgrade() -> None:
    if "is_test" in _columns():
        return
    op.add_column(
        "companies",
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_companies_is_test", "companies", ["is_test"])


def downgrade() -> None:
    if "is_test" in _columns():
        op.drop_index("ix_companies_is_test", table_name="companies")
        op.drop_column("companies", "is_test")

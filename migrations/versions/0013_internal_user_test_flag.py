"""Add a test-data marker to internal users.

Revision ID: 0013_internal_user_test
Revises: 0012_company_test_flag
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0013_internal_user_test"
down_revision = "0012_company_test_flag"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}


def upgrade() -> None:
    if "is_test" in _columns():
        return
    op.add_column("users", sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_users_is_test", "users", ["is_test"])


def downgrade() -> None:
    if "is_test" in _columns():
        op.drop_index("ix_users_is_test", table_name="users")
        op.drop_column("users", "is_test")

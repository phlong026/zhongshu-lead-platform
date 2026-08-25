"""Add auditable franchise employee-account applications.

Revision ID: 0011_company_account_req
Revises: 0010_assignment_internal
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0011_company_account_req"
down_revision = "0010_assignment_internal"
branch_labels = None
depends_on = None

_TABLE = "company_account_requests"
_COMPANY_STATUS_INDEX = "ix_company_account_requests_company_status"
_TARGET_STATUS_INDEX = "ix_company_account_requests_target_status"


def _table_exists() -> bool:
    return _TABLE in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _table_exists():
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("request_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("requested_by", sa.String(length=36), nullable=False),
        sa.Column("target_user_id", sa.String(length=36), nullable=True),
        sa.Column("requested_username", sa.String(length=64), nullable=True),
        sa.Column("requested_display_name", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(length=36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["executed_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(_COMPANY_STATUS_INDEX, _TABLE, ["company_id", "status"])
    op.create_index(_TARGET_STATUS_INDEX, _TABLE, ["target_user_id", "status"])


def downgrade() -> None:
    if _table_exists():
        op.drop_table(_TABLE)

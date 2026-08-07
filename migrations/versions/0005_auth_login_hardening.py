"""Add durable internal login throttling state.

Revision ID: 0005_auth_login_hardening
Revises: 0004_v12_reward_snapshot
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_auth_login_hardening"
down_revision = "0004_v12_reward_snapshot"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "auth_login_state" in _tables():
        return
    op.create_table(
        "auth_login_state",
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_auth_login_state_locked_until",
        "auth_login_state",
        ["locked_until"],
        unique=False,
    )


def downgrade() -> None:
    if "auth_login_state" not in _tables():
        return
    op.drop_index("ix_auth_login_state_locked_until", table_name="auth_login_state")
    op.drop_table("auth_login_state")

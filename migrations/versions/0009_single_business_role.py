"""Limit persisted accounts to one role without auto-mapping legacy accounts.

Revision ID: 0009_single_business_role
Revises: 0008_invite_used_by
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0009_single_business_role"
down_revision = "0008_invite_used_by"
branch_labels = None
depends_on = None

_CONSTRAINT_NAME = "uq_user_roles_single_business_role"
def _has_constraint(bind) -> bool:
    return any(
        item.get("name") == _CONSTRAINT_NAME
        for item in sa.inspect(bind).get_unique_constraints("user_roles")
    )


def _multiple_role_account_count(bind) -> int:
    statement = sa.text(
        """
        SELECT COUNT(*)
        FROM (
            SELECT user_id
            FROM user_roles
            GROUP BY user_id
            HAVING COUNT(*) > 1
        ) duplicate_role_accounts
        """
    )
    return int(bind.execute(statement).scalar_one())


def upgrade() -> None:
    bind = op.get_bind()
    duplicate_count = _multiple_role_account_count(bind)
    if duplicate_count:
        raise RuntimeError(
            "检测到多角色账号；请先备份并执行 "
            "scripts/migrate_five_role_accounts.py 的 dry-run 与 --apply，"
            "确认每个登录账号只保留一个五角色后再执行 Alembic 升级。"
        )
    if _has_constraint(bind):
        return
    with op.batch_alter_table("user_roles") as batch:
        batch.create_unique_constraint(_CONSTRAINT_NAME, ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_constraint(bind):
        return
    with op.batch_alter_table("user_roles") as batch:
        batch.drop_constraint(_CONSTRAINT_NAME, type_="unique")

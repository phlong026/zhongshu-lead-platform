"""Record the real user who consumed an invite (N9).

Revision ID: 0008_invite_used_by
Revises: 0007_invite_snapshot
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_invite_used_by"
down_revision = "0007_invite_snapshot"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns("invite_tokens")}


def upgrade() -> None:
    if "used_by_user_id" in _columns():
        return
    with op.batch_alter_table("invite_tokens") as batch:
        # 存量邀请没有消费归因，保持 NULL；展示层按「未记录」处理，禁止回填猜测。
        batch.add_column(sa.Column("used_by_user_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_invite_tokens_used_by_user",
            "users",
            ["used_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if "used_by_user_id" not in _columns():
        return
    with op.batch_alter_table("invite_tokens") as batch:
        # SQLite batch 模式靠整表重建，删列即连带删除其 FK，无法按名删约束；
        # PG 需要先显式删除具名外键才能删列。
        if op.get_bind().dialect.name == "postgresql":
            batch.drop_constraint("fk_invite_tokens_used_by_user", type_="foreignkey")
        batch.drop_column("used_by_user_id")

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


def _used_by_foreign_key_name(bind) -> str | None:
    """Return the actual FK constraint name on used_by_user_id, if any.

    0001 builds tables from the current ORM metadata, where PostgreSQL
    auto-names the unnamed ForeignKey as invite_tokens_used_by_user_id_fkey;
    the pure-migration path instead creates the explicit
    fk_invite_tokens_used_by_user in upgrade() below. Downgrade must resolve
    the name from the live catalog instead of assuming either spelling.
    """
    for item in sa.inspect(bind).get_foreign_keys("invite_tokens"):
        if (
            set(item.get("constrained_columns") or []) == {"used_by_user_id"}
            and item.get("referred_table") == "users"
        ):
            name = item.get("name")
            return str(name) if name else None
    return None


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
    bind = op.get_bind()
    constraint_name = _used_by_foreign_key_name(bind)
    with op.batch_alter_table("invite_tokens") as batch:
        # SQLite batch 模式靠整表重建，删列即连带删除其 FK，无法按名删约束；
        # PG 需要先显式删除具名外键才能删列。约束名以 inspector 实测为准：
        # upgrade 的守卫「列在即跳过」无法区分列由 0001 的 create_all 预建
        # （PG 自动名 invite_tokens_used_by_user_id_fkey）还是由本迁移创建
        # （显式名 fk_invite_tokens_used_by_user），按固定名删除会在混合路径
        # 下失配，因此 downgrade 必须按实测名删。
        if bind.dialect.name == "postgresql" and constraint_name:
            batch.drop_constraint(constraint_name, type_="foreignkey")
        batch.drop_column("used_by_user_id")

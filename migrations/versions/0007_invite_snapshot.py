"""Snapshot invitee/company display names on invite creation (P2-01).

Revision ID: 0007_invite_snapshot
Revises: 0006_capability_review_note
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_invite_snapshot"
down_revision = "0006_capability_review_note"
branch_labels = None
depends_on = None

# 列定义与 InviteToken 模型保持一致：长度对齐 Company.owner_name / Company.name。
_SNAPSHOT_COLUMNS: tuple[tuple[str, int], ...] = (
    ("invitee_name_snapshot", 64),
    ("company_name_snapshot", 128),
)


def _columns() -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns("invite_tokens")}


def upgrade() -> None:
    existing = _columns()
    missing = [(name, length) for name, length in _SNAPSHOT_COLUMNS if name not in existing]
    if not missing:
        return
    with op.batch_alter_table("invite_tokens") as batch:
        for name, length in missing:
            # 存量邀请没有快照，保持 NULL；前端按「未记录」展示，不回填当前值。
            batch.add_column(sa.Column(name, sa.String(length=length), nullable=True))


def downgrade() -> None:
    existing = _columns()
    droppable = [name for name, _ in _SNAPSHOT_COLUMNS if name in existing]
    if not droppable:
        return
    with op.batch_alter_table("invite_tokens") as batch:
        for name in droppable:
            batch.drop_column(name)

"""Add immutable supplier reward rule snapshots.

Revision ID: 0004_v12_reward_snapshot
Revises: 0003_v12_active_assignment
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_v12_reward_snapshot"
down_revision = "0003_v12_active_assignment"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_columns("supplier_lead_rewards")
    }


def upgrade() -> None:
    if "rule_snapshot_json" in _columns():
        return
    with op.batch_alter_table("supplier_lead_rewards") as batch:
        batch.add_column(
            sa.Column(
                "rule_snapshot_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )


def downgrade() -> None:
    if "rule_snapshot_json" not in _columns():
        return
    with op.batch_alter_table("supplier_lead_rewards") as batch:
        batch.drop_column("rule_snapshot_json")

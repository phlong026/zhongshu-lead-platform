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

DEFAULT_HARD_DUPLICATE_DAYS = 90
DEFAULT_REWARD_DUPLICATE_DAYS = 180
DEFAULT_HISTORICAL_SUSPECT_DAYS = 365


def _columns() -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_columns("supplier_lead_rewards")
    }


def _backfill_legacy_snapshots() -> None:
    """Preserve the rule facts already stored on pre-migration rewards.

    Historical rows contain their actual ratio and rule version. The previous
    implementation used the frozen V1.2 default dedup windows and no min/max
    clamp, so those facts are explicitly recorded instead of leaving an empty
    object that looks like an unknown or mutable rule.
    """

    reward = sa.table(
        "supplier_lead_rewards",
        sa.column("id", sa.String(36)),
        sa.column("reward_ratio_bps", sa.Integer()),
        sa.column("rule_version", sa.Integer()),
        sa.column("rule_snapshot_json", sa.JSON()),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(
            reward.c.id,
            reward.c.reward_ratio_bps,
            reward.c.rule_version,
        )
    ).mappings().all()
    if not rows:
        return
    statement = (
        reward.update()
        .where(reward.c.id == sa.bindparam("reward_id"))
        .values(
            rule_snapshot_json=sa.bindparam(
                "snapshot",
                type_=sa.JSON(),
            )
        )
    )
    bind.execute(
        statement,
        [
            {
                "reward_id": row["id"],
                "snapshot": {
                    "domain": "supplier_reward",
                    "key": "default",
                    "config_id": None,
                    "version": int(row["rule_version"] or 1),
                    "effective_at": None,
                    "ratio_bps": int(row["reward_ratio_bps"] or 3000),
                    "min_points": 0,
                    "max_points": None,
                    "hard_duplicate_days": DEFAULT_HARD_DUPLICATE_DAYS,
                    "reward_duplicate_days": DEFAULT_REWARD_DUPLICATE_DAYS,
                    "historical_suspect_days": DEFAULT_HISTORICAL_SUSPECT_DAYS,
                    "legacy_backfill": True,
                },
            }
            for row in rows
        ],
    )


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
    _backfill_legacy_snapshots()


def downgrade() -> None:
    if "rule_snapshot_json" not in _columns():
        return
    with op.batch_alter_table("supplier_lead_rewards") as batch:
        batch.drop_column("rule_snapshot_json")

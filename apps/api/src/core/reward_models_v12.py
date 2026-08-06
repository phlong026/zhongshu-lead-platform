from __future__ import annotations

from typing import Any

from sqlalchemy import Column, JSON

from .models_v12 import SupplierLeadReward


# V1.2.0 introduced SupplierLeadReward in models_v12. Extend it in a separate
# module so the historical 0001/0002 Alembic environment remains isolated while
# new application metadata gets a typed, queryable rule snapshot field.
if "rule_snapshot_json" not in SupplierLeadReward.__table__.c:
    SupplierLeadReward.__table__.append_column(
        Column(
            "rule_snapshot_json",
            JSON,
            nullable=False,
            default=dict,
        )
    )
if "rule_snapshot_json" not in SupplierLeadReward.__mapper__.attrs:
    SupplierLeadReward.__mapper__.add_property(
        "rule_snapshot_json",
        SupplierLeadReward.__table__.c.rule_snapshot_json,
    )


def reward_rule_snapshot(reward: SupplierLeadReward) -> dict[str, Any]:
    return dict(reward.rule_snapshot_json or {})

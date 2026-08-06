from __future__ import annotations

from datetime import datetime, timezone
from math import floor
from typing import Any

from sqlalchemy import Column, JSON, event, or_, select
from sqlalchemy.orm import Session, object_session

from .enums import ConfigStatus
from .models import SystemConfig
from .models_v12 import SupplierLeadReward
from .time import as_utc
from .v12_enums import RewardStatus

QUEUE_KEY = "v12_rewards_due_after_rejection"
SETTLING_KEY = "v12_rewards_settling_after_rejection"


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


@event.listens_for(SupplierLeadReward, "before_insert")
def apply_published_reward_rule_snapshot(_, connection, reward: SupplierLeadReward) -> None:
    """Freeze the published reward rule on every new claim reward.

    Dispatch V1.2 predates the versioned rule service and creates the reward in
    the same claim transaction. A mapper hook keeps that transaction atomic,
    replaces the legacy hard-coded percentage, and prevents later rule changes
    from rewriting historical rewards.
    """

    if reward.rule_snapshot_json:
        return
    now = datetime.now(timezone.utc)
    table = SystemConfig.__table__
    row = connection.execute(
        select(
            table.c.id,
            table.c.version,
            table.c.effective_at,
            table.c.value_json,
        )
        .where(
            table.c.domain == "supplier_reward",
            table.c.key == "default",
            table.c.status == ConfigStatus.PUBLISHED.value,
            or_(table.c.effective_at.is_(None), table.c.effective_at <= now),
        )
        .order_by(table.c.version.desc(), table.c.effective_at.desc())
        .limit(1)
    ).mappings().first()

    from ..services.reward_rule_v12 import default_supplier_reward_rule, rule_from_values

    if row:
        rule = rule_from_values(
            dict(row["value_json"] or {}),
            version=int(row["version"]),
            config_id=str(row["id"]),
            effective_at=row["effective_at"],
        )
    else:
        rule = default_supplier_reward_rule()

    reward.reward_ratio_bps = rule.ratio_bps
    reward.rule_version = rule.version
    reward.rule_snapshot_json = rule.snapshot()
    if reward.status == RewardStatus.OBSERVING.value:
        points = floor(int(reward.claim_points) * rule.ratio_bps / 10000)
        points = max(points, rule.min_points)
        if rule.max_points is not None:
            points = min(points, rule.max_points)
        reward.reward_points = max(0, int(points))
        if reward.reward_points <= 0:
            reward.status = RewardStatus.NOT_ELIGIBLE.value
            reward.observed_at = None
            reward.exception_reason = "ZERO_REWARD_POINTS"


@event.listens_for(SupplierLeadReward.status, "set", active_history=True)
def queue_overdue_reward_after_rejection(
    reward: SupplierLeadReward,
    value: str,
    old_value: str,
    _,
) -> None:
    """Queue a frozen reward for immediate settlement when an appeal is rejected."""

    if old_value != RewardStatus.FROZEN.value or value != RewardStatus.OBSERVING.value:
        return
    due_at = as_utc(reward.reward_due_at)
    if due_at is None or due_at > datetime.now(timezone.utc) or not reward.id:
        return
    session = object_session(reward)
    if session is not None:
        session.info.setdefault(QUEUE_KEY, set()).add(reward.id)


@event.listens_for(Session, "before_commit")
def settle_queued_overdue_rewards(session: Session) -> None:
    reward_ids = set(session.info.pop(QUEUE_KEY, set()))
    if not reward_ids or session.info.get(SETTLING_KEY):
        return
    session.info[SETTLING_KEY] = True
    try:
        from ..services.supplier_reward_v12 import settle_supplier_reward

        now = datetime.now(timezone.utc)
        for reward_id in sorted(reward_ids):
            settle_supplier_reward(
                session,
                reward_id=reward_id,
                as_of=now,
                settled_by=None,
            )
    finally:
        session.info.pop(SETTLING_KEY, None)


@event.listens_for(Session, "after_rollback")
def clear_queued_overdue_rewards(session: Session) -> None:
    session.info.pop(QUEUE_KEY, None)
    session.info.pop(SETTLING_KEY, None)

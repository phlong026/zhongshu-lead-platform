from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import floor
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.enums import ConfigStatus
from ..core.errors import AppError
from ..core.models import SystemConfig
from ..core.time import as_utc

settings = get_settings()

REWARD_RULE_DOMAIN = "supplier_reward"
REWARD_RULE_KEY = "default"


@dataclass(frozen=True, slots=True)
class SupplierRewardRule:
    ratio_bps: int
    min_points: int
    max_points: int | None
    hard_duplicate_days: int
    reward_duplicate_days: int
    historical_suspect_days: int
    version: int
    config_id: str | None = None
    effective_at: datetime | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "domain": REWARD_RULE_DOMAIN,
            "key": REWARD_RULE_KEY,
            "config_id": self.config_id,
            "version": self.version,
            "effective_at": self.effective_at.isoformat() if self.effective_at else None,
            "ratio_bps": self.ratio_bps,
            "min_points": self.min_points,
            "max_points": self.max_points,
            "hard_duplicate_days": self.hard_duplicate_days,
            "reward_duplicate_days": self.reward_duplicate_days,
            "historical_suspect_days": self.historical_suspect_days,
        }


def _validate_values(values: dict[str, Any]) -> dict[str, int | None]:
    try:
        ratio_bps = int(values.get("ratio_bps", 3000))
        min_points = int(values.get("min_points", 0))
        raw_max = values.get("max_points")
        max_points = int(raw_max) if raw_max is not None else None
        hard_days = int(values.get("hard_duplicate_days", settings.lead_hard_duplicate_days))
        reward_days = int(values.get("reward_duplicate_days", settings.lead_reward_duplicate_days))
        historical_days = int(
            values.get("historical_suspect_days", settings.lead_historical_suspect_days)
        )
    except (TypeError, ValueError) as exc:
        raise AppError("REWARD_RULE_INVALID", "供应商奖励规则包含非整数参数", 422) from exc
    if not 1 <= ratio_bps <= 10000:
        raise AppError("REWARD_RULE_INVALID", "奖励比例必须在 1 至 10000 个基点之间", 422)
    if min_points < 0:
        raise AppError("REWARD_RULE_INVALID", "奖励最低值不能小于 0", 422)
    if max_points is not None and max_points < min_points:
        raise AppError("REWARD_RULE_INVALID", "奖励最高值不能低于最低值", 422)
    if not (0 < hard_days < reward_days < historical_days):
        raise AppError(
            "REWARD_RULE_INVALID",
            "去重窗口必须满足 0 < 硬重复窗口 < 奖励重复窗口 < 历史疑似窗口",
            422,
        )
    return {
        "ratio_bps": ratio_bps,
        "min_points": min_points,
        "max_points": max_points,
        "hard_duplicate_days": hard_days,
        "reward_duplicate_days": reward_days,
        "historical_suspect_days": historical_days,
    }


def default_supplier_reward_rule() -> SupplierRewardRule:
    values = _validate_values({})
    return SupplierRewardRule(version=1, **values)


def rule_from_config(item: SystemConfig) -> SupplierRewardRule:
    values = _validate_values(dict(item.value_json or {}))
    return SupplierRewardRule(
        version=int(item.version),
        config_id=item.id,
        effective_at=as_utc(item.effective_at),
        **values,
    )


def resolve_supplier_reward_rule(
    db: Session,
    *,
    as_of: datetime | None = None,
) -> SupplierRewardRule:
    now = as_of or datetime.now(timezone.utc)
    item = db.scalar(
        select(SystemConfig)
        .where(
            SystemConfig.domain == REWARD_RULE_DOMAIN,
            SystemConfig.key == REWARD_RULE_KEY,
            SystemConfig.status == ConfigStatus.PUBLISHED.value,
            or_(SystemConfig.effective_at.is_(None), SystemConfig.effective_at <= now),
        )
        .order_by(SystemConfig.version.desc(), SystemConfig.effective_at.desc())
        .limit(1)
    )
    return rule_from_config(item) if item else default_supplier_reward_rule()


def calculate_reward_points(claim_points: int, rule: SupplierRewardRule) -> int:
    if claim_points <= 0:
        return 0
    points = floor(int(claim_points) * rule.ratio_bps / 10000)
    points = max(points, rule.min_points)
    if rule.max_points is not None:
        points = min(points, rule.max_points)
    return max(0, int(points))


def create_supplier_reward_rule(
    db: Session,
    *,
    values: dict[str, Any],
    created_by: str,
    publish_immediately: bool = False,
) -> SystemConfig:
    normalized = _validate_values(values)
    latest = db.scalar(
        select(SystemConfig.version)
        .where(
            SystemConfig.domain == REWARD_RULE_DOMAIN,
            SystemConfig.key == REWARD_RULE_KEY,
        )
        .order_by(SystemConfig.version.desc())
        .limit(1)
    )
    item = SystemConfig(
        domain=REWARD_RULE_DOMAIN,
        key=REWARD_RULE_KEY,
        value_json=normalized,
        version=int(latest or 0) + 1,
        status=(ConfigStatus.PUBLISHED.value if publish_immediately else ConfigStatus.DRAFT.value),
        effective_at=datetime.now(timezone.utc) if publish_immediately else None,
        published_by=created_by if publish_immediately else None,
    )
    if publish_immediately:
        retire_published_reward_rules(db)
    db.add(item)
    db.flush()
    return item


def retire_published_reward_rules(db: Session, *, exclude_id: str | None = None) -> None:
    items = db.scalars(
        select(SystemConfig).where(
            SystemConfig.domain == REWARD_RULE_DOMAIN,
            SystemConfig.key == REWARD_RULE_KEY,
            SystemConfig.status == ConfigStatus.PUBLISHED.value,
        )
    ).all()
    for item in items:
        if exclude_id and item.id == exclude_id:
            continue
        item.status = ConfigStatus.RETIRED.value


def publish_supplier_reward_rule(
    db: Session,
    *,
    config_id: str,
    published_by: str,
) -> SystemConfig:
    item = db.get(SystemConfig, config_id)
    if (
        item is None
        or item.domain != REWARD_RULE_DOMAIN
        or item.key != REWARD_RULE_KEY
    ):
        raise AppError("REWARD_RULE_NOT_FOUND", "供应商奖励规则不存在", 404)
    _validate_values(dict(item.value_json or {}))
    if item.status == ConfigStatus.PUBLISHED.value:
        return item
    retire_published_reward_rules(db, exclude_id=item.id)
    item.status = ConfigStatus.PUBLISHED.value
    item.effective_at = datetime.now(timezone.utc)
    item.published_by = published_by
    db.flush()
    return item


def reward_rule_config_to_dict(item: SystemConfig) -> dict[str, Any]:
    rule = rule_from_config(item)
    return {
        "id": item.id,
        "domain": item.domain,
        "key": item.key,
        "version": item.version,
        "status": item.status,
        "effective_at": item.effective_at.isoformat() if item.effective_at else None,
        "published_by": item.published_by,
        "value": rule.snapshot(),
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }

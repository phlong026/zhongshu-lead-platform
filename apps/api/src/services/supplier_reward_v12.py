from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.enums import PointsLedgerType
from ..core.errors import AppError
from ..core.models import PointsAccount, PointsLedger, ReturnRequest
from ..core.models_v12 import SupplierLeadReward
from ..core.state_machine_v12 import assert_reward_transition
from ..core.time import as_utc
from ..core.v12_enums import ReturnV12Status, RewardStatus
from .points_service import change_points, get_or_create_account

VALID_REVERSAL_REASONS = {"FRAUD", "SYSTEM_ERROR", "ADMIN_ERROR"}
ACTIVE_APPEAL_STATUSES = {
    ReturnV12Status.VERIFYING.value,
    ReturnV12Status.REVIEWING.value,
    ReturnV12Status.NEED_MORE_EVIDENCE.value,
    ReturnV12Status.APPROVED.value,
}


@dataclass(frozen=True, slots=True)
class RewardSettlementResult:
    reward: SupplierLeadReward
    ledger: PointsLedger | None
    idempotent: bool = False
    frozen: bool = False


@dataclass(frozen=True, slots=True)
class RewardReversalResult:
    reward: SupplierLeadReward
    ledger: PointsLedger
    idempotent: bool = False


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return as_utc(current) or current


def get_reward(db: Session, reward_id: str, *, lock: bool = False) -> SupplierLeadReward:
    stmt = select(SupplierLeadReward).where(SupplierLeadReward.id == reward_id)
    if lock:
        stmt = stmt.with_for_update()
    reward = db.scalar(stmt)
    if reward is None:
        raise AppError("SUPPLIER_REWARD_NOT_FOUND", "供应商奖励不存在", 404)
    return reward


def _active_appeal_exists(db: Session, assignment_id: str) -> bool:
    return db.scalar(
        select(ReturnRequest.id)
        .where(
            ReturnRequest.assignment_id == assignment_id,
            ReturnRequest.submitted_at.is_not(None),
            ReturnRequest.status.in_(ACTIVE_APPEAL_STATUSES),
        )
        .limit(1)
    ) is not None


def settle_supplier_reward(
    db: Session,
    *,
    reward_id: str,
    as_of: datetime | None = None,
    settled_by: str | None = None,
    require_due: bool = True,
) -> RewardSettlementResult:
    reward = get_reward(db, reward_id, lock=True)
    existing_ledger = db.get(PointsLedger, reward.ledger_id) if reward.ledger_id else None
    if reward.status == RewardStatus.SETTLED.value:
        if existing_ledger is None:
            raise AppError("REWARD_LEDGER_MISSING", "奖励已结算但积分流水缺失", 500)
        return RewardSettlementResult(reward=reward, ledger=existing_ledger, idempotent=True)
    if reward.status == RewardStatus.FROZEN.value:
        return RewardSettlementResult(reward=reward, ledger=None, frozen=True)
    if reward.status != RewardStatus.OBSERVING.value:
        raise AppError(
            "REWARD_NOT_SETTLEABLE",
            "奖励当前不可结算",
            409,
            {"status": reward.status},
        )

    now = _now(as_of)
    due_at = as_utc(reward.reward_due_at)
    if require_due and (due_at is None or due_at > now):
        raise AppError(
            "REWARD_NOT_DUE",
            "奖励尚未到结算时间",
            409,
            {"reward_due_at": due_at.isoformat() if due_at else None},
        )
    if _active_appeal_exists(db, reward.assignment_id):
        assert_reward_transition(RewardStatus.OBSERVING, RewardStatus.FROZEN)
        reward.status = RewardStatus.FROZEN.value
        reward.frozen_at = reward.frozen_at or now
        db.flush()
        return RewardSettlementResult(reward=reward, ledger=None, frozen=True)
    if int(reward.reward_points) <= 0:
        raise AppError("REWARD_POINTS_INVALID", "奖励积分必须大于 0 才能结算", 409)

    ledger = change_points(
        db,
        company_id=reward.supplier_company_id,
        delta=int(reward.reward_points),
        ledger_type=PointsLedgerType.REWARD.value,
        business_type="V12_SUPPLIER_REWARD",
        business_id=reward.id,
        idempotency_key=f"v12-reward:{reward.id}:settle",
        created_by=settled_by,
        metadata={
            "assignment_id": reward.assignment_id,
            "lead_id": reward.lead_id,
            "receiver_company_id": reward.receiver_company_id,
            "claim_points": int(reward.claim_points),
            "reward_ratio_bps": int(reward.reward_ratio_bps),
            "reward_points": int(reward.reward_points),
            "rule_version": int(reward.rule_version),
            "rule_snapshot": dict(reward.rule_snapshot_json or {}),
        },
    )
    assert_reward_transition(RewardStatus.OBSERVING, RewardStatus.SETTLED)
    reward.status = RewardStatus.SETTLED.value
    reward.settled_at = now
    reward.ledger_id = ledger.id
    reward.exception_reason = None
    db.flush()
    return RewardSettlementResult(reward=reward, ledger=ledger)


def _select_due_reward_ids(
    db: Session,
    *,
    as_of: datetime,
    limit: int,
    exclude_reward_ids: set[str] | None = None,
) -> list[str]:
    filters = [
        SupplierLeadReward.status == RewardStatus.OBSERVING.value,
        SupplierLeadReward.reward_due_at.is_not(None),
        SupplierLeadReward.reward_due_at <= as_of,
    ]
    if exclude_reward_ids:
        filters.append(SupplierLeadReward.id.not_in(exclude_reward_ids))
    return list(
        db.scalars(
            select(SupplierLeadReward.id)
            .where(*filters)
            .order_by(SupplierLeadReward.reward_due_at.asc(), SupplierLeadReward.id.asc())
            .limit(max(1, min(int(limit), 1000)))
        ).all()
    )


def run_due_supplier_reward_settlement(
    db: Session,
    *,
    as_of: datetime | None = None,
    limit: int = 100,
    settled_by: str | None = None,
    exclude_reward_ids: set[str] | None = None,
) -> dict[str, Any]:
    now = _now(as_of)
    reward_ids = _select_due_reward_ids(
        db,
        as_of=now,
        limit=limit,
        exclude_reward_ids=exclude_reward_ids,
    )
    settled = 0
    idempotent = 0
    frozen = 0
    skipped = 0
    failed = 0
    errors: list[dict[str, str]] = []
    for reward_id in reward_ids:
        try:
            with db.begin_nested():
                result = settle_supplier_reward(
                    db,
                    reward_id=reward_id,
                    as_of=now,
                    settled_by=settled_by,
                )
                if result.frozen:
                    frozen += 1
                elif result.idempotent:
                    idempotent += 1
                else:
                    settled += 1
        except AppError as exc:
            if exc.code in {"REWARD_NOT_DUE", "REWARD_NOT_SETTLEABLE"}:
                skipped += 1
            else:
                failed += 1
                errors.append({"reward_id": reward_id, "code": exc.code, "message": exc.message})
        except Exception as exc:  # pragma: no cover - defensive scheduler boundary
            failed += 1
            errors.append({"reward_id": reward_id, "code": "UNEXPECTED", "message": str(exc)})
    return {
        "scanned": len(reward_ids),
        "settled": settled,
        "idempotent": idempotent,
        "frozen": frozen,
        "skipped": skipped,
        "failed": failed,
        "errors": errors[:20],
        "processed_reward_ids": reward_ids,
        "as_of": now.isoformat(),
    }


def drain_due_supplier_reward_settlement(
    db: Session,
    *,
    as_of: datetime | None = None,
    batch_size: int = 500,
    max_batches: int = 20,
    settled_by: str | None = None,
) -> dict[str, Any]:
    """Drain due rewards without letting a bad oldest row block valid rows.

    Each reward is attempted at most once per drain cycle. Failed rows remain
    OBSERVING and are retried by the next hourly cycle; later valid rows can
    still settle now. The safety bound caps one cycle at 20,000 rows because
    batch_size itself is capped at 1,000.
    """

    now = _now(as_of)
    safe_batch_size = max(1, min(int(batch_size), 1000))
    safe_max_batches = max(1, min(int(max_batches), 100))
    attempted: set[str] = set()
    totals: dict[str, Any] = {
        "batches": 0,
        "scanned": 0,
        "settled": 0,
        "idempotent": 0,
        "frozen": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "as_of": now.isoformat(),
    }
    for _ in range(safe_max_batches):
        result = run_due_supplier_reward_settlement(
            db,
            as_of=now,
            limit=safe_batch_size,
            settled_by=settled_by,
            exclude_reward_ids=attempted,
        )
        reward_ids = set(result.pop("processed_reward_ids", []))
        if not reward_ids:
            break
        attempted.update(reward_ids)
        totals["batches"] += 1
        for key in ("scanned", "settled", "idempotent", "frozen", "skipped", "failed"):
            totals[key] += int(result[key])
        totals["errors"].extend(result.get("errors", []))
        if int(result["scanned"]) < safe_batch_size:
            break

    remaining_due = len(
        _select_due_reward_ids(
            db,
            as_of=now,
            limit=1,
            exclude_reward_ids=attempted,
        )
    )
    totals["errors"] = totals["errors"][:50]
    totals["attempted_unique"] = len(attempted)
    totals["safety_limit_reached"] = bool(remaining_due)
    return totals


def _change_points_allow_negative(
    db: Session,
    *,
    company_id: str,
    delta: int,
    business_id: str,
    idempotency_key: str,
    related_ledger_id: str,
    created_by: str,
    metadata: dict[str, Any],
) -> PointsLedger:
    existing = db.scalar(
        select(PointsLedger).where(
            PointsLedger.company_id == company_id,
            PointsLedger.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return existing
    account = db.scalar(
        select(PointsAccount).where(PointsAccount.company_id == company_id).with_for_update()
    )
    if account is None:
        account = get_or_create_account(db, company_id)
    account.balance = int(account.balance) + int(delta)
    account.version += 1
    ledger = PointsLedger(
        account_id=account.id,
        company_id=company_id,
        ledger_type=PointsLedgerType.REVERSAL.value,
        delta=delta,
        balance_after=int(account.balance),
        business_type="V12_SUPPLIER_REWARD_REVERSAL",
        business_id=business_id,
        idempotency_key=idempotency_key,
        related_ledger_id=related_ledger_id,
        metadata_json=metadata,
        created_by=created_by,
    )
    db.add(ledger)
    db.flush()
    return ledger


def reverse_supplier_reward(
    db: Session,
    *,
    reward_id: str,
    reason_code: str,
    note: str,
    reversed_by: str,
    as_of: datetime | None = None,
) -> RewardReversalResult:
    reward = get_reward(db, reward_id, lock=True)
    normalized_reason = reason_code.strip().upper()
    if normalized_reason not in VALID_REVERSAL_REASONS:
        raise AppError("REWARD_REVERSAL_REASON_INVALID", "奖励冲正原因无效", 422)
    if reward.status == RewardStatus.REVERSED.value:
        ledger = db.get(PointsLedger, reward.reversal_ledger_id) if reward.reversal_ledger_id else None
        if ledger is None:
            raise AppError("REWARD_REVERSAL_LEDGER_MISSING", "奖励已冲正但冲正流水缺失", 500)
        return RewardReversalResult(reward=reward, ledger=ledger, idempotent=True)
    if reward.status != RewardStatus.SETTLED.value:
        raise AppError(
            "REWARD_NOT_REVERSIBLE",
            "仅已结算奖励允许异常冲正",
            409,
            {"status": reward.status},
        )
    original = db.get(PointsLedger, reward.ledger_id) if reward.ledger_id else None
    if original is None or original.business_type != "V12_SUPPLIER_REWARD":
        raise AppError("REWARD_LEDGER_MISSING", "未找到原奖励结算流水", 409)

    ledger = _change_points_allow_negative(
        db,
        company_id=reward.supplier_company_id,
        delta=-abs(int(original.delta)),
        business_id=reward.id,
        idempotency_key=f"v12-reward:{reward.id}:reverse",
        related_ledger_id=original.id,
        created_by=reversed_by,
        metadata={
            "reason_code": normalized_reason,
            "note": note.strip(),
            "original_ledger_id": original.id,
            "assignment_id": reward.assignment_id,
            "lead_id": reward.lead_id,
        },
    )
    assert_reward_transition(RewardStatus.SETTLED, RewardStatus.REVERSED)
    reward.status = RewardStatus.REVERSED.value
    reward.reversed_at = _now(as_of)
    reward.reversal_ledger_id = ledger.id
    reward.exception_reason = f"{normalized_reason}: {note.strip()}"
    db.flush()
    return RewardReversalResult(reward=reward, ledger=ledger)


def reward_to_dict(reward: SupplierLeadReward) -> dict[str, Any]:
    return {
        "id": reward.id,
        "lead_id": reward.lead_id,
        "assignment_id": reward.assignment_id,
        "supplier_company_id": reward.supplier_company_id,
        "receiver_company_id": reward.receiver_company_id,
        "status": reward.status,
        "claim_points": int(reward.claim_points),
        "reward_ratio_bps": int(reward.reward_ratio_bps),
        "reward_points": int(reward.reward_points),
        "rule_version": int(reward.rule_version),
        "rule_snapshot": dict(reward.rule_snapshot_json or {}),
        "observed_at": reward.observed_at.isoformat() if reward.observed_at else None,
        "appeal_deadline_at": reward.appeal_deadline_at.isoformat()
        if reward.appeal_deadline_at
        else None,
        "reward_due_at": reward.reward_due_at.isoformat() if reward.reward_due_at else None,
        "frozen_at": reward.frozen_at.isoformat() if reward.frozen_at else None,
        "settled_at": reward.settled_at.isoformat() if reward.settled_at else None,
        "cancelled_at": reward.cancelled_at.isoformat() if reward.cancelled_at else None,
        "reversed_at": reward.reversed_at.isoformat() if reward.reversed_at else None,
        "ledger_id": reward.ledger_id,
        "reversal_ledger_id": reward.reversal_ledger_id,
        "exception_reason": reward.exception_reason,
        "created_at": reward.created_at.isoformat(),
        "updated_at": reward.updated_at.isoformat(),
    }


def supplier_reward_summary(db: Session, supplier_company_id: str) -> dict[str, int]:
    rows = db.execute(
        select(
            SupplierLeadReward.status,
            func.count(SupplierLeadReward.id),
            func.coalesce(func.sum(SupplierLeadReward.reward_points), 0),
        )
        .where(SupplierLeadReward.supplier_company_id == supplier_company_id)
        .group_by(SupplierLeadReward.status)
    ).all()
    result: dict[str, int] = {
        "total_count": 0,
        "settled_points": 0,
        "observing_points": 0,
        "frozen_points": 0,
    }
    for status, count, points in rows:
        result["total_count"] += int(count)
        if status == RewardStatus.SETTLED.value:
            result["settled_points"] += int(points)
        elif status == RewardStatus.OBSERVING.value:
            result["observing_points"] += int(points)
        elif status == RewardStatus.FROZEN.value:
            result["frozen_points"] += int(points)
    return result

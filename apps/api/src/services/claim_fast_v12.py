from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.enums import AssignmentStatus, PointsLedgerType
from ..core.errors import AppError
from ..core.models import Assignment, AssignmentEvent, Lead, PointsLedger
from ..core.models_v12 import CalendarDay, SupplierLeadReward
from ..core.security import decrypt_text
from ..core.time import as_utc
from ..core.v12_enums import DuplicateDecision, LeadV12Status, RewardStatus
from .company_profile_v12 import require_lead_capability
from .dispatch_v12 import (
    CLAIMED_CONTACT_STATUSES,
    ClaimResult,
    _receiver_duplicate_assignment,
    _region_matches,
    get_dispatch_lead,
)
from .points_service import change_points
from .reward_rule_v12 import calculate_reward_points, resolve_supplier_reward_rule


settings = get_settings()


@dataclass(frozen=True, slots=True)
class ClaimExecution:
    result: ClaimResult
    lead: Lead


def _claim_deadline(db: Session, moment: datetime, workdays: int = 3) -> datetime:
    """Resolve the normal 3-workday deadline with one query and exact fallback."""

    if workdays <= 0:
        return moment
    horizon_days = max(31, workdays * 7)
    end_day = (moment + timedelta(days=horizon_days)).date()
    rows = db.scalars(
        select(CalendarDay).where(
            CalendarDay.day > moment.date(),
            CalendarDay.day <= end_day,
        )
    ).all()
    overrides = {row.day: bool(row.is_workday) for row in rows}
    cursor = moment
    remaining = workdays
    while remaining and cursor.date() < end_day:
        cursor += timedelta(days=1)
        if overrides.get(cursor.date(), cursor.weekday() < 5):
            remaining -= 1

    # Three workdays should normally resolve in the batched window. If an
    # operator configured an unusually long holiday/non-workday period, retain
    # the exact CalendarDay semantics instead of silently falling back to Monday-Friday.
    while remaining:
        cursor += timedelta(days=1)
        item = db.get(CalendarDay, cursor.date())
        if bool(item.is_workday) if item is not None else cursor.weekday() < 5:
            remaining -= 1
    return cursor


def _reward_for_claim_fast(
    db: Session,
    *,
    lead: Lead,
    assignment: Assignment,
    now: datetime,
    deadline: datetime,
    rule,
) -> SupplierLeadReward | None:
    if not lead.supplier_company_id or lead.supplier_company_id == assignment.company_id:
        return None
    existing = db.scalar(
        select(SupplierLeadReward).where(SupplierLeadReward.assignment_id == assignment.id)
    )
    if existing:
        return existing

    eligible = lead.duplicate_status not in {
        DuplicateDecision.HARD_DUPLICATE.value,
        DuplicateDecision.REWARD_DUPLICATE.value,
    }
    reward_points = calculate_reward_points(int(assignment.points_price), rule) if eligible else 0
    reward_status = RewardStatus.OBSERVING.value if eligible and reward_points > 0 else RewardStatus.NOT_ELIGIBLE.value
    reward = SupplierLeadReward(
        lead_id=lead.id,
        assignment_id=assignment.id,
        supplier_company_id=lead.supplier_company_id,
        receiver_company_id=assignment.company_id,
        status=reward_status,
        claim_points=int(assignment.points_price),
        reward_ratio_bps=rule.ratio_bps,
        reward_points=reward_points,
        rule_version=rule.version,
        rule_snapshot_json=rule.snapshot(),
        observed_at=now if reward_status == RewardStatus.OBSERVING.value else None,
        appeal_deadline_at=deadline,
        reward_due_at=deadline,
        exception_reason=(
            None
            if reward_status == RewardStatus.OBSERVING.value
            else "REWARD_DUPLICATE" if not eligible else "ZERO_REWARD_POINTS"
        ),
    )
    db.add(reward)
    return reward


def claim_assignment_fast(
    db: Session,
    *,
    assignment_id: str,
    company_id: str,
    claimed_by: str,
) -> ClaimExecution:
    """Authoritative V1.2 claim path with a shorter lock-held critical section."""

    assignment = db.scalar(
        select(Assignment)
        .where(Assignment.id == assignment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if assignment is None:
        raise AppError("ASSIGNMENT_NOT_FOUND", "派发单不存在", 404)
    if assignment.company_id != company_id:
        raise AppError("ASSIGNMENT_FORBIDDEN", "无权领取其他公司的派发单", 403)

    existing_ledger = db.scalar(
        select(PointsLedger).where(
            PointsLedger.company_id == company_id,
            PointsLedger.idempotency_key == f"v12-claim:{assignment.id}",
        )
    )
    if assignment.status in CLAIMED_CONTACT_STATUSES:
        if existing_ledger is None:
            raise AppError("CLAIM_LEDGER_MISSING", "派发单已领取但积分流水缺失", 500)
        lead = get_dispatch_lead(db, assignment.lead_id)
        reward = db.scalar(
            select(SupplierLeadReward).where(SupplierLeadReward.assignment_id == assignment.id)
        )
        return ClaimExecution(
            result=ClaimResult(
                assignment=assignment,
                ledger=existing_ledger,
                reward=reward,
                phone=decrypt_text(lead.phone_encrypted),
                idempotent=True,
            ),
            lead=lead,
        )
    if assignment.status != AssignmentStatus.PENDING_CLAIM.value:
        raise AppError(
            "ASSIGNMENT_NOT_CLAIMABLE",
            "派发单当前不可领取",
            409,
            {"status": assignment.status},
        )

    now = datetime.now(timezone.utc)
    expires_at = as_utc(assignment.expires_at)
    if expires_at and expires_at <= now:
        raise AppError("ASSIGNMENT_EXPIRED", "派发单已过期", 409)

    require_lead_capability(db, company_id, "LEAD_RECEIVER")
    lead = get_dispatch_lead(db, assignment.lead_id, lock=True)
    if lead.current_assignment_id != assignment.id or lead.status != LeadV12Status.DISPATCHED.value:
        raise AppError("LEAD_ASSIGNMENT_CONFLICT", "客资与派发单状态不一致", 409)
    if lead.supplier_company_id and lead.supplier_company_id == company_id:
        raise AppError("SELF_SUPPLY_FORBIDDEN", "供应商不得领取自己上传的客资", 409)
    if not _region_matches(db, company_id, lead):
        raise AppError("SERVICE_REGION_MISMATCH", "公司当前服务区域已不匹配该客资", 409)

    reward_rule = resolve_supplier_reward_rule(db, as_of=now)
    duplicate = _receiver_duplicate_assignment(
        db,
        lead=lead,
        company_id=company_id,
        exclude_assignment_id=assignment.id,
        now=now,
        reward_rule=reward_rule,
    )
    if duplicate:
        raise AppError(
            "DUPLICATE_TO_RECEIVER",
            "该客户已由当前公司历史领取",
            409,
            {"assignment_id": duplicate.id},
        )

    # change_points owns the single PointsAccount serialization boundary. The
    # previous HTTP claim path acquired the same account row lock before calling
    # change_points, which then acquired it again.
    ledger = change_points(
        db,
        company_id=company_id,
        delta=-int(assignment.points_price),
        ledger_type=PointsLedgerType.CLAIM.value,
        business_type="V12_ASSIGNMENT_CLAIM",
        business_id=assignment.id,
        idempotency_key=f"v12-claim:{assignment.id}",
        created_by=claimed_by,
        metadata={"lead_id": lead.id, "points_price": int(assignment.points_price)},
    )

    deadline = _claim_deadline(db, now, 3)
    assignment.status = AssignmentStatus.CLAIMED.value
    assignment.claimed_at = now
    assignment.claim_points = int(assignment.points_price)
    assignment.appeal_deadline_at = deadline
    assignment.reward_due_at = deadline
    assignment.receiver_company_id = company_id
    assignment.supplier_company_id = lead.supplier_company_id
    assignment.first_followup_due_at = now + timedelta(hours=settings.first_followup_hours)
    lead.status = LeadV12Status.CLAIMED.value
    lead.current_follow_status = "UNCONTACTED"

    reward = _reward_for_claim_fast(
        db,
        lead=lead,
        assignment=assignment,
        now=now,
        deadline=deadline,
        rule=reward_rule,
    )
    if reward is not None:
        db.flush()

    db.add(
        AssignmentEvent(
            assignment_id=assignment.id,
            event_type="V12_CLAIMED",
            actor_user_id=claimed_by,
            payload={
                "lead_id": lead.id,
                "company_id": company_id,
                "points": int(assignment.points_price),
                "ledger_id": ledger.id,
                "appeal_deadline_at": deadline.isoformat(),
                "reward_id": reward.id if reward else None,
            },
        )
    )
    db.flush()
    return ClaimExecution(
        result=ClaimResult(
            assignment=assignment,
            ledger=ledger,
            reward=reward,
            phone=decrypt_text(lead.phone_encrypted),
            idempotent=False,
        ),
        lead=lead,
    )

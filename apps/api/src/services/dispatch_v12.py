from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import floor
from typing import Any

from sqlalchemy import Index, func, or_, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.enums import ACTIVE_ASSIGNMENT_STATUSES, AssignmentStatus, PointsLedgerType
from ..core.errors import AppError
from ..core.models import Assignment, AssignmentEvent, Company, Lead, PointsAccount, PointsLedger
from ..core.models_v12 import CompanyServiceAreaV12, SupplierLeadReward
from ..core.security import decrypt_text, mask_phone
from ..core.time import as_utc
from ..core.v12_enums import DuplicateDecision, LeadV12Status, RewardStatus
from .company_profile_v12 import has_lead_capability, require_lead_capability
from .points_service import change_points, resolve_price
from .workday_calendar import WorkdayCalendarService

settings = get_settings()

ACTIVE_ASSIGNMENT_STATUS_VALUES = tuple(item.value for item in ACTIVE_ASSIGNMENT_STATUSES)
CLAIMED_CONTACT_STATUSES = {
    AssignmentStatus.CLAIMED.value,
    AssignmentStatus.FOLLOWING.value,
    AssignmentStatus.RETURN_PENDING.value,
    AssignmentStatus.COMPLETED.value,
}
RECEIVER_HISTORY_STATUSES = CLAIMED_CONTACT_STATUSES

# Base.metadata.create_all is still used in development and tests. Register the
# same partial unique index that migration 0003 creates for PostgreSQL/SQLite.
_active_assignment_predicate = Assignment.__table__.c.status.in_(ACTIVE_ASSIGNMENT_STATUS_VALUES)
if not any(index.name == "uq_assignments_active_lead_v12" for index in Assignment.__table__.indexes):
    Index(
        "uq_assignments_active_lead_v12",
        Assignment.__table__.c.lead_id,
        unique=True,
        sqlite_where=_active_assignment_predicate,
        postgresql_where=_active_assignment_predicate,
    )


@dataclass(frozen=True, slots=True)
class CandidateResult:
    company_id: str
    company_name: str
    eligible: bool
    exclusion_reasons: tuple[str, ...]
    points_price: int
    price_rule_id: str | None
    price_version: int
    points_balance: int
    points_reserved: int
    points_available: int
    region_match: bool
    duplicate_to_receiver: bool


@dataclass(frozen=True, slots=True)
class ClaimResult:
    assignment: Assignment
    ledger: PointsLedger
    reward: SupplierLeadReward | None
    phone: str | None
    idempotent: bool


def get_dispatch_lead(db: Session, lead_id: str, *, lock: bool = False) -> Lead:
    stmt = select(Lead).where(Lead.id == lead_id)
    if lock:
        stmt = stmt.with_for_update()
    lead = db.scalar(stmt)
    if lead is None:
        raise AppError("LEAD_NOT_FOUND", "客资不存在", 404)
    return lead


def _region_matches(db: Session, company_id: str, lead: Lead) -> bool:
    if not lead.region_code:
        return False
    return db.scalar(
        select(CompanyServiceAreaV12.id).where(
            CompanyServiceAreaV12.company_id == company_id,
            CompanyServiceAreaV12.region_code == lead.region_code,
            CompanyServiceAreaV12.active.is_(True),
            CompanyServiceAreaV12.review_status == "APPROVED",
        )
    ) is not None


def _points_snapshot(db: Session, company_id: str, *, lock_account: bool = False) -> tuple[int, int, int]:
    """Read balance/reservations without creating an account during a GET.

    Dispatch calls this while the company row and points account are locked, so
    two concurrent manual dispatches cannot reserve the same points twice.
    """

    stmt = select(PointsAccount).where(PointsAccount.company_id == company_id)
    if lock_account:
        stmt = stmt.with_for_update()
    account = db.scalar(stmt)
    balance = int(account.balance) if account is not None else 0
    reserved = db.scalar(
        select(func.coalesce(func.sum(Assignment.points_price), 0)).where(
            Assignment.company_id == company_id,
            Assignment.status == AssignmentStatus.PENDING_CLAIM.value,
        )
    ) or 0
    return balance, int(reserved), balance - int(reserved)


def _receiver_duplicate_assignment(
    db: Session,
    *,
    lead: Lead,
    company_id: str,
    exclude_assignment_id: str | None = None,
    now: datetime | None = None,
) -> Assignment | None:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=settings.lead_historical_suspect_days)
    match_clauses = [Lead.phone_hash == lead.phone_hash]
    if lead.phone_fingerprint:
        match_clauses.insert(0, Lead.phone_fingerprint == lead.phone_fingerprint)
    filters = [
        Assignment.company_id == company_id,
        Assignment.status.in_(RECEIVER_HISTORY_STATUSES),
        Assignment.claimed_at.is_not(None),
        Assignment.claimed_at >= cutoff,
        Assignment.lead_id != lead.id,
        or_(*match_clauses),
    ]
    if exclude_assignment_id:
        filters.append(Assignment.id != exclude_assignment_id)
    return db.scalar(
        select(Assignment)
        .join(Lead, Lead.id == Assignment.lead_id)
        .where(*filters)
        .order_by(Assignment.claimed_at.desc())
        .limit(1)
    )


def evaluate_candidate(
    db: Session,
    *,
    lead: Lead,
    company: Company,
    lock_account: bool = False,
) -> CandidateResult:
    reasons: list[str] = []
    if company.status != "ACTIVE":
        reasons.append("COMPANY_INACTIVE")
    if not has_lead_capability(db, company.id, "LEAD_RECEIVER"):
        reasons.append("RECEIVER_CAPABILITY_REQUIRED")
    if lead.supplier_company_id and lead.supplier_company_id == company.id:
        reasons.append("SELF_SUPPLY_FORBIDDEN")
    region_match = _region_matches(db, company.id, lead)
    if not region_match:
        reasons.append("SERVICE_REGION_MISMATCH")
    duplicate_assignment = _receiver_duplicate_assignment(db, lead=lead, company_id=company.id)
    if duplicate_assignment is not None:
        reasons.append("DUPLICATE_TO_RECEIVER")
    points_price, rule = resolve_price(db, lead, company)
    balance, reserved, available = _points_snapshot(db, company.id, lock_account=lock_account)
    if available < points_price:
        reasons.append("POINTS_INSUFFICIENT")
    return CandidateResult(
        company_id=company.id,
        company_name=company.name,
        eligible=not reasons,
        exclusion_reasons=tuple(reasons),
        points_price=points_price,
        price_rule_id=rule.id if rule else None,
        price_version=rule.version if rule else 1,
        points_balance=balance,
        points_reserved=reserved,
        points_available=available,
        region_match=region_match,
        duplicate_to_receiver=duplicate_assignment is not None,
    )


def list_candidates(db: Session, *, lead: Lead) -> list[CandidateResult]:
    companies = db.scalars(select(Company).order_by(Company.name.asc(), Company.id.asc())).all()
    return [evaluate_candidate(db, lead=lead, company=company) for company in companies]


def list_dispatch_pool(
    db: Session,
    *,
    region_code: str | None = None,
    source_kind: str | None = None,
    page_no: int = 1,
    page_size: int = 20,
) -> tuple[list[Lead], int]:
    filters = [
        Lead.status == LeadV12Status.READY_DISPATCH.value,
        Lead.current_assignment_id.is_(None),
    ]
    if region_code:
        filters.append(Lead.region_code == region_code)
    if source_kind:
        filters.append(Lead.source_kind == source_kind)
    total = db.scalar(select(func.count(Lead.id)).where(*filters)) or 0
    items = db.scalars(
        select(Lead)
        .where(*filters)
        .order_by(Lead.submitted_at.asc(), Lead.created_at.asc())
        .offset((page_no - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), int(total)


def dispatch_manually(
    db: Session,
    *,
    lead_id: str,
    company_id: str,
    assigned_by: str,
    idempotency_key: str,
    note: str | None = None,
) -> Assignment:
    existing = db.scalar(select(Assignment).where(Assignment.idempotency_key == idempotency_key))
    if existing:
        if existing.lead_id != lead_id or existing.company_id != company_id:
            raise AppError("IDEMPOTENCY_CONFLICT", "幂等键已被其他派发请求使用", 409)
        return existing

    lead = get_dispatch_lead(db, lead_id, lock=True)

    # A same-key request may have completed while this transaction waited for
    # the lead lock. Recheck before validating the now-transitioned lead state.
    existing = db.scalar(select(Assignment).where(Assignment.idempotency_key == idempotency_key))
    if existing:
        if existing.lead_id != lead_id or existing.company_id != company_id:
            raise AppError("IDEMPOTENCY_CONFLICT", "幂等键已被其他派发请求使用", 409)
        return existing

    if lead.status != LeadV12Status.READY_DISPATCH.value or lead.current_assignment_id:
        raise AppError(
            "LEAD_NOT_READY_DISPATCH",
            "客资当前不在待派发池",
            409,
            {"status": lead.status, "current_assignment_id": lead.current_assignment_id},
        )
    active = db.scalar(
        select(Assignment).where(
            Assignment.lead_id == lead.id,
            Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUS_VALUES),
        )
    )
    if active:
        raise AppError("LEAD_ALREADY_ASSIGNED", "客资已有有效派发单", 409, {"assignment_id": active.id})

    # Serialize point reservations for this receiver. Company creation normally
    # creates the points account; locking the company also covers missing legacy
    # accounts without introducing a read-side mutation.
    company = db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    if company is None:
        raise AppError("COMPANY_NOT_FOUND", "目标公司不存在", 404)
    candidate = evaluate_candidate(db, lead=lead, company=company, lock_account=True)
    if not candidate.eligible:
        raise AppError(
            "DISPATCH_CANDIDATE_INELIGIBLE",
            "目标公司不符合本次派发条件",
            409,
            {"reasons": list(candidate.exclusion_reasons)},
        )

    now = datetime.now(timezone.utc)
    phone = decrypt_text(lead.phone_encrypted)
    assignment = Assignment(
        lead_id=lead.id,
        company_id=company.id,
        receiver_company_id=company.id,
        supplier_company_id=lead.supplier_company_id,
        status=AssignmentStatus.PENDING_CLAIM.value,
        points_price=candidate.points_price,
        claim_points=candidate.points_price,
        price_rule_id=candidate.price_rule_id,
        price_version=candidate.price_version,
        lead_snapshot={
            "customer_name": lead.customer_name,
            "phone_masked": mask_phone(phone),
            "region_code": lead.region_code,
            "city": lead.city,
            "district": lead.district,
            "category_code": lead.category_code,
            "brand_code": lead.brand_code,
            "need_summary": lead.need_summary,
            "source_kind": lead.source_kind,
            "duplicate_status": lead.duplicate_status,
            "note": note.strip() if note else None,
        },
        assigned_by=assigned_by,
        assigned_at=now,
        expires_at=now + timedelta(hours=settings.assignment_expire_hours),
        idempotency_key=idempotency_key,
    )
    db.add(assignment)
    db.flush()
    lead.status = LeadV12Status.DISPATCHED.value
    lead.current_assignment_id = assignment.id
    db.add(
        AssignmentEvent(
            assignment_id=assignment.id,
            event_type="V12_MANUAL_DISPATCH",
            actor_user_id=assigned_by,
            payload={
                "lead_id": lead.id,
                "company_id": company.id,
                "points_price": candidate.points_price,
                "price_rule_id": candidate.price_rule_id,
                "manual": True,
            },
        )
    )
    db.flush()
    return assignment


def _reward_for_claim(
    db: Session,
    *,
    lead: Lead,
    assignment: Assignment,
    now: datetime,
    deadline: datetime,
) -> SupplierLeadReward | None:
    if not lead.supplier_company_id or lead.supplier_company_id == assignment.company_id:
        return None
    existing = db.scalar(select(SupplierLeadReward).where(SupplierLeadReward.assignment_id == assignment.id))
    if existing:
        return existing
    eligible = lead.duplicate_status not in {
        DuplicateDecision.HARD_DUPLICATE.value,
        DuplicateDecision.REWARD_DUPLICATE.value,
    }
    ratio_bps = 3000
    reward_points = floor(int(assignment.points_price) * ratio_bps / 10000) if eligible else 0
    reward = SupplierLeadReward(
        lead_id=lead.id,
        assignment_id=assignment.id,
        supplier_company_id=lead.supplier_company_id,
        receiver_company_id=assignment.company_id,
        status=RewardStatus.OBSERVING.value if eligible else RewardStatus.NOT_ELIGIBLE.value,
        claim_points=int(assignment.points_price),
        reward_ratio_bps=ratio_bps,
        reward_points=reward_points,
        rule_version=1,
        observed_at=now if eligible else None,
        appeal_deadline_at=deadline,
        reward_due_at=deadline,
        exception_reason=None if eligible else "REWARD_DUPLICATE",
    )
    db.add(reward)
    db.flush()
    return reward


def claim_assignment(
    db: Session,
    *,
    assignment_id: str,
    company_id: str,
    claimed_by: str,
) -> ClaimResult:
    assignment = db.scalar(select(Assignment).where(Assignment.id == assignment_id).with_for_update())
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
        reward = db.scalar(select(SupplierLeadReward).where(SupplierLeadReward.assignment_id == assignment.id))
        return ClaimResult(
            assignment=assignment,
            ledger=existing_ledger,
            reward=reward,
            phone=decrypt_text(lead.phone_encrypted),
            idempotent=True,
        )
    if assignment.status != AssignmentStatus.PENDING_CLAIM.value:
        raise AppError("ASSIGNMENT_NOT_CLAIMABLE", "派发单当前不可领取", 409, {"status": assignment.status})

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
    duplicate = _receiver_duplicate_assignment(
        db,
        lead=lead,
        company_id=company_id,
        exclude_assignment_id=assignment.id,
        now=now,
    )
    if duplicate:
        raise AppError(
            "DUPLICATE_TO_RECEIVER",
            "该客户已由当前公司历史领取",
            409,
            {"assignment_id": duplicate.id},
        )

    account = db.scalar(
        select(PointsAccount).where(PointsAccount.company_id == company_id).with_for_update()
    )
    if account is None or int(account.balance) < int(assignment.points_price):
        raise AppError(
            "POINTS_INSUFFICIENT",
            "积分不足，无法领取客资",
            409,
            {"balance": int(account.balance) if account else 0, "required": int(assignment.points_price)},
        )
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

    deadline = WorkdayCalendarService(db).add_workdays(now, 3)
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
    reward = _reward_for_claim(db, lead=lead, assignment=assignment, now=now, deadline=deadline)
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
    return ClaimResult(
        assignment=assignment,
        ledger=ledger,
        reward=reward,
        phone=decrypt_text(lead.phone_encrypted),
        idempotent=False,
    )


def lead_pool_item(lead: Lead) -> dict[str, Any]:
    return {
        "id": lead.id,
        "customer_name": lead.customer_name,
        "phone_masked": mask_phone(decrypt_text(lead.phone_encrypted)),
        "city": lead.city,
        "district": lead.district,
        "region_code": lead.region_code,
        "category_code": lead.category_code,
        "brand_code": lead.brand_code,
        "need_summary": lead.need_summary,
        "source_kind": lead.source_kind,
        "supplier_company_id": lead.supplier_company_id,
        "duplicate_status": lead.duplicate_status,
        "status": lead.status,
        "submitted_at": lead.submitted_at.isoformat() if lead.submitted_at else None,
        "created_at": lead.created_at.isoformat(),
    }


def candidate_to_dict(item: CandidateResult, *, include_financials: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "company_id": item.company_id,
        "company_name": item.company_name,
        "eligible": item.eligible,
        "exclusion_reasons": list(item.exclusion_reasons),
        "points_price": item.points_price,
        "price_rule_id": item.price_rule_id,
        "price_version": item.price_version,
        "region_match": item.region_match,
        "duplicate_to_receiver": item.duplicate_to_receiver,
    }
    if include_financials:
        data.update(
            {
                "points_balance": item.points_balance,
                "points_reserved": item.points_reserved,
                "points_available": item.points_available,
            }
        )
    return data

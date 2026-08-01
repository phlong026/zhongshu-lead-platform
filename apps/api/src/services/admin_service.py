from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.auth import Principal
from ..core.enums import AssignmentStatus, LeadStatus, ReturnStatus
from ..core.models import (
    Assignment,
    Company,
    FollowUp,
    Lead,
    NotificationOutbox,
    PointsAccount,
    PointsLedger,
    ReturnRequest,
    VerificationTask,
)


def _count(db: Session, model, *criteria) -> int:
    stmt = select(func.count()).select_from(model)
    if criteria:
        stmt = stmt.where(*criteria)
    return int(db.scalar(stmt) or 0)


def _rate(numerator: int, denominator: int) -> float:
    return round((numerator / denominator * 100), 2) if denominator else 0.0


def dashboard_summary(db: Session, principal: Principal) -> dict[str, Any]:
    """Return a role-aware summary without leaking financial data to operations."""
    business = {
        "staging": _count(db, Lead, Lead.status.in_([LeadStatus.IMPORTED, LeadStatus.IMPORT_ERROR, LeadStatus.DUPLICATE_REVIEW])),
        "verification_pending": _count(db, VerificationTask, VerificationTask.status.in_(["PENDING", "ASSIGNED", "IN_PROGRESS"])),
        "qualified": _count(db, Lead, Lead.status == LeadStatus.QUALIFIED),
        "pending_claim": _count(db, Assignment, Assignment.status == AssignmentStatus.PENDING_CLAIM),
        "claimed": _count(db, Assignment, Assignment.status.in_([AssignmentStatus.CLAIMED, AssignmentStatus.FOLLOWING])),
        "return_pending": _count(db, ReturnRequest, ReturnRequest.status.in_([ReturnStatus.PENDING, ReturnStatus.NEED_MORE])),
        "completed": _count(db, Assignment, Assignment.status == AssignmentStatus.COMPLETED),
        "active_companies": _count(db, Company, Company.status == "ACTIVE"),
        "total_leads": _count(db, Lead),
        "assignments_total": _count(db, Assignment),
        "claimed_total": _count(db, Assignment, Assignment.claimed_at.is_not(None)),
        "followed_total": int(db.scalar(select(func.count(func.distinct(FollowUp.assignment_id)))) or 0),
    }
    business["claim_rate"] = _rate(business["claimed_total"], business["assignments_total"])
    business["followup_rate"] = _rate(business["followed_total"], business["claimed_total"])
    business["conversion_rate"] = _rate(business["completed"], business["claimed_total"])
    response: dict[str, Any] = {"business": business}

    if principal.can("dashboard.finance.read") or principal.can("points.read") or principal.can("*"):
        account_total = int(db.scalar(select(func.coalesce(func.sum(PointsAccount.balance), 0))) or 0)
        recharged = int(
            db.scalar(
                select(func.coalesce(func.sum(PointsLedger.delta), 0)).where(
                    PointsLedger.ledger_type == "RECHARGE",
                    PointsLedger.delta > 0,
                )
            )
            or 0
        )
        consumed = abs(
            int(
                db.scalar(
                    select(func.coalesce(func.sum(PointsLedger.delta), 0)).where(
                        PointsLedger.ledger_type == "CLAIM",
                        PointsLedger.delta < 0,
                    )
                )
                or 0
            )
        )
        refunded = int(
            db.scalar(
                select(func.coalesce(func.sum(PointsLedger.delta), 0)).where(
                    PointsLedger.ledger_type == "RETURN",
                    PointsLedger.delta > 0,
                )
            )
            or 0
        )
        response["finance"] = {
            "points_balance_total": account_total,
            "points_recharged_total": recharged,
            "points_consumed_total": consumed,
            "points_refunded_total": refunded,
        }

    if principal.has_any_role("FRANCHISE_OWNER"):
        company_id = principal.company_id
        response["business"] = {
            "pending_claim": _count(db, Assignment, Assignment.company_id == company_id, Assignment.status == AssignmentStatus.PENDING_CLAIM),
            "claimed": _count(db, Assignment, Assignment.company_id == company_id, Assignment.status.in_([AssignmentStatus.CLAIMED, AssignmentStatus.FOLLOWING])),
            "return_pending": _count(db, ReturnRequest, ReturnRequest.company_id == company_id, ReturnRequest.status.in_([ReturnStatus.PENDING, ReturnStatus.NEED_MORE])),
            "completed": _count(db, Assignment, Assignment.company_id == company_id, Assignment.status == AssignmentStatus.COMPLETED),
        }
        account = db.scalar(select(PointsAccount).where(PointsAccount.company_id == company_id))
        response["points"] = {"balance": int(account.balance) if account else 0}
    return response


def dashboard_performance(db: Session, principal: Principal, *, days: int = 30) -> dict[str, Any]:
    """Return period funnel, regional performance and finance without leaking money fields."""
    start = datetime.now(timezone.utc) - timedelta(days=days)
    leads_created = _count(db, Lead, Lead.created_at >= start)
    qualified = _count(db, Lead, Lead.created_at >= start, Lead.status == LeadStatus.QUALIFIED)
    assignments = _count(db, Assignment, Assignment.created_at >= start)
    claimed = _count(db, Assignment, Assignment.created_at >= start, Assignment.claimed_at.is_not(None))
    followed = int(
        db.scalar(
            select(func.count(func.distinct(FollowUp.assignment_id)))
            .join(Assignment, Assignment.id == FollowUp.assignment_id)
            .where(Assignment.created_at >= start)
        )
        or 0
    )
    completed = _count(db, Assignment, Assignment.created_at >= start, Assignment.status == AssignmentStatus.COMPLETED)
    returns = _count(db, ReturnRequest, ReturnRequest.created_at >= start)

    lead_regions = db.execute(
        select(Lead.city, func.count(Lead.id))
        .where(Lead.created_at >= start)
        .group_by(Lead.city)
    ).all()
    assignment_regions = db.execute(
        select(Lead.city, func.count(Assignment.id))
        .join(Lead, Lead.id == Assignment.lead_id)
        .where(Assignment.created_at >= start)
        .group_by(Lead.city)
    ).all()
    completed_regions = db.execute(
        select(Lead.city, func.count(Assignment.id))
        .join(Lead, Lead.id == Assignment.lead_id)
        .where(Assignment.created_at >= start, Assignment.status == AssignmentStatus.COMPLETED)
        .group_by(Lead.city)
    ).all()
    region_data: dict[str, dict[str, Any]] = {}
    for city, count in lead_regions:
        region_data[city or "未标注"] = {"region": city or "未标注", "leads": int(count), "assignments": 0, "completed": 0}
    for city, count in assignment_regions:
        item = region_data.setdefault(city or "未标注", {"region": city or "未标注", "leads": 0, "assignments": 0, "completed": 0})
        item["assignments"] = int(count)
    for city, count in completed_regions:
        item = region_data.setdefault(city or "未标注", {"region": city or "未标注", "leads": 0, "assignments": 0, "completed": 0})
        item["completed"] = int(count)
    regions = sorted(region_data.values(), key=lambda item: (item["leads"], item["assignments"]), reverse=True)
    for item in regions:
        item["dispatch_rate"] = _rate(item["assignments"], item["leads"])
        item["conversion_rate"] = _rate(item["completed"], item["assignments"])

    response: dict[str, Any] = {
        "days": days,
        "period_start": start.isoformat(),
        "funnel": {
            "leads_created": leads_created,
            "qualified": qualified,
            "assignments": assignments,
            "claimed": claimed,
            "followed": followed,
            "completed": completed,
            "returns": returns,
            "qualification_rate": _rate(qualified, leads_created),
            "claim_rate": _rate(claimed, assignments),
            "followup_rate": _rate(followed, claimed),
            "conversion_rate": _rate(completed, claimed),
            "return_rate": _rate(returns, claimed),
        },
        "regions": regions[:50],
    }

    if principal.can("dashboard.finance.read") or principal.can("points.read") or principal.can("*"):
        recharged = int(db.scalar(select(func.coalesce(func.sum(PointsLedger.delta), 0)).where(PointsLedger.created_at >= start, PointsLedger.ledger_type == "RECHARGE", PointsLedger.delta > 0)) or 0)
        consumed = abs(int(db.scalar(select(func.coalesce(func.sum(PointsLedger.delta), 0)).where(PointsLedger.created_at >= start, PointsLedger.ledger_type == "CLAIM", PointsLedger.delta < 0)) or 0))
        refunded = int(db.scalar(select(func.coalesce(func.sum(PointsLedger.delta), 0)).where(PointsLedger.created_at >= start, PointsLedger.ledger_type == "RETURN", PointsLedger.delta > 0)) or 0)
        response["finance"] = {
            "points_recharged": recharged,
            "points_consumed": consumed,
            "points_refunded": refunded,
            "net_points_change": recharged - consumed + refunded,
        }
    return response


def dashboard_trends(db: Session, *, days: int = 7) -> dict[str, Any]:
    start = datetime.now(timezone.utc) - timedelta(days=days - 1)
    labels = [(start + timedelta(days=i)).date().isoformat() for i in range(days)]
    lead_counter: Counter[str] = Counter()
    assignment_counter: Counter[str] = Counter()
    followup_counter: Counter[str] = Counter()

    for created_at in db.scalars(select(Lead.created_at).where(Lead.created_at >= start)).all():
        lead_counter[created_at.date().isoformat()] += 1
    for created_at in db.scalars(select(Assignment.created_at).where(Assignment.created_at >= start)).all():
        assignment_counter[created_at.date().isoformat()] += 1
    for created_at in db.scalars(select(FollowUp.created_at).where(FollowUp.created_at >= start)).all():
        followup_counter[created_at.date().isoformat()] += 1

    return {
        "labels": labels,
        "series": {
            "leads": [lead_counter[x] for x in labels],
            "assignments": [assignment_counter[x] for x in labels],
            "followups": [followup_counter[x] for x in labels],
        },
    }


def source_distribution(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Lead.source_channel, func.count(Lead.id)).group_by(Lead.source_channel).order_by(func.count(Lead.id).desc())
    ).all()
    return [{"source": source or "未标注", "count": int(count)} for source, count in rows]


def operational_alerts(db: Session) -> dict[str, Any]:
    return {
        "failed_notifications": _count(db, NotificationOutbox, NotificationOutbox.status.in_(["FAILED", "DEAD"])),
        "import_errors": _count(db, Lead, Lead.status == LeadStatus.IMPORT_ERROR),
        "duplicate_reviews": _count(db, Lead, Lead.status == LeadStatus.DUPLICATE_REVIEW),
        "return_reviews": _count(db, ReturnRequest, ReturnRequest.status.in_([ReturnStatus.PENDING, ReturnStatus.NEED_MORE])),
    }

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, literal, select, union_all
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
    funnel = db.execute(
        select(
            select(func.count(Lead.id)).where(Lead.created_at >= start).scalar_subquery(),
            select(func.count(Lead.id))
            .where(Lead.created_at >= start, Lead.status == LeadStatus.QUALIFIED)
            .scalar_subquery(),
            select(func.count(Assignment.id)).where(Assignment.created_at >= start).scalar_subquery(),
            select(func.count(Assignment.id))
            .where(Assignment.created_at >= start, Assignment.claimed_at.is_not(None))
            .scalar_subquery(),
            select(func.count(func.distinct(FollowUp.assignment_id)))
            .join(Assignment, Assignment.id == FollowUp.assignment_id)
            .where(Assignment.created_at >= start)
            .scalar_subquery(),
            select(func.count(Assignment.id))
            .where(Assignment.created_at >= start, Assignment.status == AssignmentStatus.COMPLETED)
            .scalar_subquery(),
            select(func.count(ReturnRequest.id))
            .where(ReturnRequest.created_at >= start)
            .scalar_subquery(),
        )
    ).one()
    leads_created, qualified, assignments, claimed, followed, completed, returns = (
        int(value or 0) for value in funnel
    )

    regional_counts = union_all(
        select(
            Lead.city.label("region"),
            func.count(Lead.id).label("leads"),
            literal(0).label("assignments"),
            literal(0).label("completed"),
        )
        .where(Lead.created_at >= start)
        .group_by(Lead.city),
        select(
            Lead.city.label("region"),
            literal(0).label("leads"),
            func.count(Assignment.id).label("assignments"),
            literal(0).label("completed"),
        )
        .join(Lead, Lead.id == Assignment.lead_id)
        .where(Assignment.created_at >= start)
        .group_by(Lead.city),
        select(
            Lead.city.label("region"),
            literal(0).label("leads"),
            literal(0).label("assignments"),
            func.count(Assignment.id).label("completed"),
        )
        .join(Lead, Lead.id == Assignment.lead_id)
        .where(Assignment.created_at >= start, Assignment.status == AssignmentStatus.COMPLETED)
        .group_by(Lead.city),
    ).subquery()
    regional_rows = db.execute(
        select(
            regional_counts.c.region,
            func.sum(regional_counts.c.leads),
            func.sum(regional_counts.c.assignments),
            func.sum(regional_counts.c.completed),
        ).group_by(regional_counts.c.region)
    ).all()
    region_data: dict[str, dict[str, Any]] = {}
    for city, lead_count, assignment_count, completed_count in regional_rows:
        region = city or "未标注"
        region_data[region] = {
            "region": region,
            "leads": int(lead_count or 0),
            "assignments": int(assignment_count or 0),
            "completed": int(completed_count or 0),
        }
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
        finance = db.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (PointsLedger.ledger_type == "RECHARGE") & (PointsLedger.delta > 0),
                                PointsLedger.delta,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (PointsLedger.ledger_type == "CLAIM") & (PointsLedger.delta < 0),
                                PointsLedger.delta,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (PointsLedger.ledger_type == "RETURN") & (PointsLedger.delta > 0),
                                PointsLedger.delta,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(PointsLedger.created_at >= start)
        ).one()
        recharged = int(finance[0] or 0)
        consumed = abs(int(finance[1] or 0))
        refunded = int(finance[2] or 0)
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
        "failed_notifications": _count(db, NotificationOutbox, NotificationOutbox.status.in_(["FAILED", "DEAD", "MANUAL_ACTION_REQUIRED"])),
        "import_errors": _count(db, Lead, Lead.status == LeadStatus.IMPORT_ERROR),
        "duplicate_reviews": _count(db, Lead, Lead.status == LeadStatus.DUPLICATE_REVIEW),
        "return_reviews": _count(db, ReturnRequest, ReturnRequest.status.in_([ReturnStatus.PENDING, ReturnStatus.NEED_MORE])),
    }

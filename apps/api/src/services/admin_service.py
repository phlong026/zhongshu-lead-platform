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
    }
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

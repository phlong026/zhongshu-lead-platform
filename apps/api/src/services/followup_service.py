from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.auth import Principal
from ..core.enums import AssignmentStatus, FollowStatus, LeadStatus
from ..core.errors import AppError
from ..core.models import Assignment, AssignmentEvent, FollowUp, Lead, Notification
from .notification_service import create_station_message, enqueue_outbox


def add_followup(
    db: Session,
    *,
    assignment: Assignment,
    principal: Principal,
    status: str,
    note: str | None,
    next_followup_at: datetime | None,
) -> FollowUp:
    if assignment.company_id != principal.company_id:
        raise AppError("FORBIDDEN", "无权更新该客资", 403)
    if assignment.status not in {AssignmentStatus.CLAIMED, AssignmentStatus.FOLLOWING}:
        raise AppError("FOLLOWUP_NOT_ALLOWED", "订单当前不可跟进", 409)
    followup = FollowUp(
        assignment_id=assignment.id,
        company_id=assignment.company_id,
        status=status,
        note=note.strip() if note else None,
        next_followup_at=next_followup_at,
        created_by=principal.user_id,
    )
    db.add(followup)
    assignment.status = AssignmentStatus.COMPLETED if status == FollowStatus.DEAL else AssignmentStatus.FOLLOWING
    lead = db.get(Lead, assignment.lead_id)
    if lead:
        lead.current_follow_status = status
        if status == FollowStatus.DEAL:
            lead.status = LeadStatus.CLOSED
        else:
            lead.status = LeadStatus.FOLLOWING
    db.add(
        AssignmentEvent(
            assignment_id=assignment.id,
            event_type="FOLLOWUP_ADDED",
            actor_user_id=principal.user_id,
            payload={"status": status, "next_followup_at": next_followup_at.isoformat() if next_followup_at else None},
        )
    )
    enqueue_outbox(
        db,
        event_key=f"assignment:{assignment.id}:followup:{followup.id}",
        event_type="FOLLOWUP_ADDED",
        aggregate_type="assignment",
        aggregate_id=assignment.id,
        payload={"company_id": assignment.company_id, "status": status},
    )
    db.flush()
    return followup


def followup_to_dict(item: FollowUp) -> dict[str, Any]:
    return {
        "id": item.id,
        "assignment_id": item.assignment_id,
        "status": item.status,
        "note": item.note,
        "next_followup_at": item.next_followup_at.isoformat() if item.next_followup_at else None,
        "created_at": item.created_at.isoformat(),
    }


def overdue_followups(db: Session, now: datetime | None = None) -> list[Assignment]:
    now = now or datetime.now(timezone.utc)
    return db.scalars(
        select(Assignment).where(
            Assignment.status.in_([AssignmentStatus.CLAIMED, AssignmentStatus.FOLLOWING]),
            Assignment.first_followup_due_at.is_not(None),
            Assignment.first_followup_due_at <= now,
            ~select(FollowUp.id).where(FollowUp.assignment_id == Assignment.id).exists(),
        )
    ).all()


def run_followup_overdue(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Create one durable reminder per overdue assignment.

    The outbox event key and station-message lookup make the job safe to rerun
    from the API, CLI or scheduler without generating duplicate reminders.
    """
    assignments = overdue_followups(db, now=now)
    notified = 0
    for assignment in assignments:
        deep_link = f"/h5/#/lead/{assignment.id}"
        existing = db.scalar(
            select(Notification.id).where(
                Notification.company_id == assignment.company_id,
                Notification.scene == "FOLLOWUP_OVERDUE",
                Notification.deep_link == deep_link,
            )
        )
        if not existing:
            create_station_message(
                db,
                user_id=None,
                company_id=assignment.company_id,
                scene="FOLLOWUP_OVERDUE",
                title="客资待跟进",
                body="该客资已超过首次跟进时限，请尽快反馈。",
                deep_link=deep_link,
            )
            notified += 1
        enqueue_outbox(
            db,
            event_key=f"assignment:{assignment.id}:followup-overdue",
            event_type="FOLLOWUP_OVERDUE",
            aggregate_type="assignment",
            aggregate_id=assignment.id,
            payload={"company_id": assignment.company_id, "deep_link": deep_link},
        )
    return {"overdue": len(assignments), "notified": notified}

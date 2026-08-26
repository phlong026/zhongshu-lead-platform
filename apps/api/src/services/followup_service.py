from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.auth import Principal
from ..core.enums import AssignmentStatus, FollowStatus, LeadStatus
from ..core.errors import AppError
from ..core.models import Assignment, AssignmentEvent, FollowUp, Lead, Notification
from .company_assignment_v12 import require_company_assignment_access
from .notification_service import create_station_message, enqueue_outbox
from .supplier_reward_v12 import activate_supplier_reward_after_effective_confirmation


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def add_followup(
    db: Session,
    *,
    assignment: Assignment,
    principal: Principal,
    status: str,
    note: str | None,
    next_followup_at: datetime | None,
) -> FollowUp:
    require_company_assignment_access(principal, assignment)
    if assignment.status not in {AssignmentStatus.CLAIMED, AssignmentStatus.FOLLOWING}:
        raise AppError("FOLLOWUP_NOT_ALLOWED", "订单当前不可跟进", 409)
    normalized_status = status.strip().upper()
    if normalized_status == FollowStatus.INVALID.value:
        raise AppError(
            "FOLLOWUP_INVALID_REQUIRES_RETURN",
            "无效客资必须发起正式退回申诉，由运营完成后续处置",
            409,
        )
    next_followup_at = _as_utc(next_followup_at)
    followup = FollowUp(
        assignment_id=assignment.id,
        company_id=assignment.company_id,
        status=normalized_status,
        note=note.strip() if note else None,
        next_followup_at=next_followup_at,
        created_by=principal.user_id,
    )
    db.add(followup)
    assignment.status = AssignmentStatus.COMPLETED if normalized_status == FollowStatus.DEAL else AssignmentStatus.FOLLOWING
    lead = db.get(Lead, assignment.lead_id)
    if lead:
        lead.current_follow_status = normalized_status
        if normalized_status == FollowStatus.DEAL:
            lead.status = LeadStatus.CLOSED
        else:
            lead.status = LeadStatus.FOLLOWING
    db.add(
        AssignmentEvent(
            assignment_id=assignment.id,
            event_type="FOLLOWUP_ADDED",
            actor_user_id=principal.user_id,
            payload={"status": normalized_status, "next_followup_at": next_followup_at.isoformat() if next_followup_at else None},
        )
    )
    enqueue_outbox(
        db,
        event_key=f"assignment:{assignment.id}:followup:{followup.id}",
        event_type="FOLLOWUP_ADDED",
        aggregate_type="assignment",
        aggregate_id=assignment.id,
        payload={"company_id": assignment.company_id, "status": normalized_status},
    )
    if normalized_status == FollowStatus.DEAL.value:
        activate_supplier_reward_after_effective_confirmation(db, assignment_id=assignment.id)
    db.flush()
    return followup


def followup_to_dict(item: FollowUp) -> dict[str, Any]:
    next_followup_at = _as_utc(item.next_followup_at)
    created_at = _as_utc(item.created_at)
    return {
        "id": item.id,
        "assignment_id": item.assignment_id,
        "status": item.status,
        "note": item.note,
        "next_followup_at": next_followup_at.isoformat() if next_followup_at else None,
        "created_at": created_at.isoformat() if created_at else None,
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


def _followup_deep_links(assignment: Assignment) -> tuple[str, tuple[str, ...]]:
    legacy_link = f"/h5/#/lead/{assignment.id}"
    if getattr(assignment, "receiver_company_id", None):
        v12_link = f"/h5/v12-workbench.html?view=assignments&id={assignment.id}"
        return v12_link, (v12_link, legacy_link)
    return legacy_link, (legacy_link,)


def run_followup_overdue(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Create one durable reminder per overdue assignment.

    V1.2 assignments deep-link to the V1.2 workbench. The lookup also accepts the
    historical hash link so upgrading an already-overdue assignment does not create a
    second station message. The outbox event key keeps delivery retries idempotent.
    """
    assignments = overdue_followups(db, now=now)
    notified = 0
    for assignment in assignments:
        deep_link, compatible_links = _followup_deep_links(assignment)
        existing = db.scalar(
            select(Notification.id).where(
                Notification.company_id == assignment.company_id,
                Notification.scene == "FOLLOWUP_OVERDUE",
                Notification.deep_link.in_(compatible_links),
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

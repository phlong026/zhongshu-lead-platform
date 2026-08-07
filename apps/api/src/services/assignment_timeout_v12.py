from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.enums import AssignmentStatus
from ..core.models import Assignment, AssignmentEvent, Lead
from ..core.time import as_utc
from ..core.v12_enums import LeadV12Status
from .claim_service import run_assignment_timeouts as run_assignment_timeouts_legacy
from .notification_service import create_station_message, enqueue_outbox

settings = get_settings()


def run_assignment_timeouts_active(db: Session) -> dict[str, int]:
    """Route every supported timeout entrypoint through the active business version."""

    if settings.legacy_write_enabled:
        return run_assignment_timeouts_legacy(db)
    return run_assignment_timeouts_v12(db)


def run_assignment_timeouts_v12(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    """Expire only active V1.2 manual dispatches and return their leads to the V1.2 pool.

    A V1.2 pending assignment is identified by the lead/assignment invariant created by
    dispatch_manually: the lead is DISPATCHED and points at the same current_assignment_id.
    Historical V1.0.1 pending assignments are deliberately not mutated here.

    Candidate discovery selects only primary keys. Each row is then reloaded under a
    database lock with ``populate_existing`` so a worker that waited for another worker
    cannot act on stale ``reminder_sent_at`` or status values from SQLAlchemy's identity map.
    """

    current = as_utc(now) or datetime.now(timezone.utc)
    reminded = 0
    expired = 0
    pending_ids = db.scalars(
        select(Assignment.id)
        .join(Lead, Lead.id == Assignment.lead_id)
        .where(
            Assignment.status == AssignmentStatus.PENDING_CLAIM.value,
            Lead.status == LeadV12Status.DISPATCHED.value,
            Lead.current_assignment_id == Assignment.id,
        )
        .order_by(Assignment.assigned_at.asc(), Assignment.id.asc())
    ).all()

    for assignment_id in pending_ids:
        assignment = db.scalar(
            select(Assignment)
            .where(Assignment.id == assignment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if assignment is None or assignment.status != AssignmentStatus.PENDING_CLAIM.value:
            continue
        lead = db.scalar(
            select(Lead)
            .where(Lead.id == assignment.lead_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            lead is None
            or lead.current_assignment_id != assignment.id
            or lead.status != LeadV12Status.DISPATCHED.value
        ):
            continue

        assigned_at = as_utc(assignment.assigned_at) or current
        expires_at = as_utc(assignment.expires_at)
        hours = max(0.0, (current - assigned_at).total_seconds() / 3600)
        is_expired = bool(expires_at and expires_at <= current) or hours >= settings.assignment_expire_hours

        if is_expired:
            assignment.status = AssignmentStatus.EXPIRED.value
            assignment.released_at = current
            assignment.release_reason = "UNCLAIMED_TIMEOUT"
            lead.current_assignment_id = None
            lead.status = LeadV12Status.READY_DISPATCH.value
            lead.pending_reason = "UNCLAIMED_TIMEOUT"
            db.add(
                AssignmentEvent(
                    assignment_id=assignment.id,
                    event_type="V12_ASSIGNMENT_EXPIRED",
                    payload={"hours": hours, "lead_id": lead.id},
                )
            )
            enqueue_outbox(
                db,
                event_key=f"v12-assignment:{assignment.id}:expired",
                event_type="V12_ASSIGNMENT_EXPIRED",
                aggregate_type="assignment",
                aggregate_id=assignment.id,
                payload={"company_id": assignment.company_id, "lead_id": lead.id},
            )
            expired += 1
            continue

        if hours >= settings.assignment_reminder_hours and assignment.reminder_sent_at is None:
            assignment.reminder_sent_at = current
            create_station_message(
                db,
                user_id=None,
                company_id=assignment.company_id,
                scene="V12_CLAIM_REMINDER",
                title="客资即将过期",
                body="该客资尚未领取，请尽快处理。",
                deep_link=f"/h5/v12-workbench.html?view=assignments&id={assignment.id}",
            )
            enqueue_outbox(
                db,
                event_key=f"v12-assignment:{assignment.id}:reminder",
                event_type="V12_ASSIGNMENT_REMINDER",
                aggregate_type="assignment",
                aggregate_id=assignment.id,
                payload={"company_id": assignment.company_id, "lead_id": lead.id},
            )
            reminded += 1

    return {"reminded": reminded, "expired": expired}

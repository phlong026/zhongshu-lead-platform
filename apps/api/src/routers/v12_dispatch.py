from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.auth import require_permissions
from ..core.database import get_db
from ..core.enums import AssignmentStatus
from ..core.errors import AppError
from ..core.models import Assignment, Lead
from ..core.responses import ok, page
from ..core.security import decrypt_text, mask_phone
from ..core.v12_enums import LeadV12Status
from ..schemas.v12_dispatch import ManualDispatchBody
from ..services.audit import write_audit
from ..services.company_profile_v12 import require_active_company
from ..services.dispatch_v12 import (
    candidate_to_dict,
    claim_assignment,
    dispatch_manually,
    get_dispatch_lead,
    lead_pool_item,
    list_candidates,
    list_dispatch_pool,
)

router = APIRouter(prefix="/v1.2", tags=["v1.2-dispatch-claim"])


def _assignment_dict(assignment: Assignment, lead: Lead, *, reveal_phone: bool = False) -> dict:
    phone = decrypt_text(lead.phone_encrypted)
    return {
        "id": assignment.id,
        "lead_id": assignment.lead_id,
        "company_id": assignment.company_id,
        "supplier_company_id": assignment.supplier_company_id,
        "receiver_company_id": assignment.receiver_company_id,
        "status": assignment.status,
        "points_price": assignment.points_price,
        "claim_points": assignment.claim_points,
        "price_rule_id": assignment.price_rule_id,
        "price_version": assignment.price_version,
        "customer_name": lead.customer_name,
        "phone": phone if reveal_phone else None,
        "phone_masked": mask_phone(phone),
        "city": lead.city,
        "district": lead.district,
        "region_code": lead.region_code,
        "need_summary": lead.need_summary,
        "assigned_at": assignment.assigned_at.isoformat(),
        "expires_at": assignment.expires_at.isoformat() if assignment.expires_at else None,
        "claimed_at": assignment.claimed_at.isoformat() if assignment.claimed_at else None,
        "appeal_deadline_at": assignment.appeal_deadline_at.isoformat() if assignment.appeal_deadline_at else None,
        "reward_due_at": assignment.reward_due_at.isoformat() if assignment.reward_due_at else None,
        "first_followup_due_at": assignment.first_followup_due_at.isoformat() if assignment.first_followup_due_at else None,
    }


@router.get("/dispatch-pool")
def dispatch_pool(
    request: Request,
    principal=Depends(require_permissions("lead.dispatch")),
    db: Session = Depends(get_db),
    region_code: str | None = Query(default=None),
    source_kind: str | None = Query(default=None),
    page_no: int = Query(default=1, alias="page", ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    items, total = list_dispatch_pool(
        db,
        region_code=region_code,
        source_kind=source_kind.strip().upper() if source_kind else None,
        page_no=page_no,
        page_size=page_size,
    )
    return ok(request, page([lead_pool_item(item) for item in items], total, page_no, page_size))


@router.get("/dispatch-pool/{lead_id}/candidates")
def dispatch_candidates(
    lead_id: str,
    request: Request,
    principal=Depends(require_permissions("lead.dispatch")),
    db: Session = Depends(get_db),
):
    lead = get_dispatch_lead(db, lead_id)
    if lead.status != LeadV12Status.READY_DISPATCH.value:
        raise AppError("LEAD_NOT_READY_DISPATCH", "客资当前不在待派发池", 409, {"status": lead.status})
    items = list_candidates(db, lead=lead)
    return ok(
        request,
        {
            "lead": lead_pool_item(lead),
            "eligible_count": sum(1 for item in items if item.eligible),
            "candidates": [candidate_to_dict(item) for item in items],
        },
    )


@router.post("/dispatch-pool/{lead_id}/dispatch")
def manual_dispatch(
    lead_id: str,
    body: ManualDispatchBody,
    request: Request,
    principal=Depends(require_permissions("lead.dispatch")),
    db: Session = Depends(get_db),
):
    assignment = dispatch_manually(
        db,
        lead_id=lead_id,
        company_id=body.company_id,
        assigned_by=principal.user_id,
        idempotency_key=body.idempotency_key,
        note=body.note,
    )
    lead = get_dispatch_lead(db, lead_id)
    write_audit(
        db,
        principal=principal,
        action="V12_MANUAL_DISPATCH",
        resource_type="assignment",
        resource_id=assignment.id,
        company_id=assignment.company_id,
        after={
            "lead_id": lead_id,
            "company_id": assignment.company_id,
            "status": assignment.status,
            "points_price": assignment.points_price,
            "manual": True,
        },
        reason=body.note,
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, _assignment_dict(assignment, lead), "客资已人工派发")


@router.get("/assignments")
def own_assignments(
    request: Request,
    principal=Depends(require_permissions("assignment.own.read")),
    db: Session = Depends(get_db),
    status: str | None = Query(default=None),
    page_no: int = Query(default=1, alias="page", ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    company = require_active_company(db, principal.company_id)
    filters = [Assignment.company_id == company.id]
    if status:
        filters.append(Assignment.status == status.strip().upper())
    total = db.scalar(select(func.count(Assignment.id)).where(*filters)) or 0
    rows = db.execute(
        select(Assignment, Lead)
        .join(Lead, Lead.id == Assignment.lead_id)
        .where(*filters)
        .order_by(Assignment.assigned_at.desc())
        .offset((page_no - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        _assignment_dict(
            assignment,
            lead,
            reveal_phone=assignment.status
            in {
                AssignmentStatus.CLAIMED.value,
                AssignmentStatus.FOLLOWING.value,
                AssignmentStatus.RETURN_PENDING.value,
                AssignmentStatus.COMPLETED.value,
            },
        )
        for assignment, lead in rows
    ]
    return ok(request, page(items, int(total), page_no, page_size))


@router.get("/assignments/{assignment_id}")
def own_assignment_detail(
    assignment_id: str,
    request: Request,
    principal=Depends(require_permissions("assignment.own.read")),
    db: Session = Depends(get_db),
):
    company = require_active_company(db, principal.company_id)
    row = db.execute(
        select(Assignment, Lead)
        .join(Lead, Lead.id == Assignment.lead_id)
        .where(Assignment.id == assignment_id, Assignment.company_id == company.id)
    ).one_or_none()
    if row is None:
        raise AppError("ASSIGNMENT_NOT_FOUND", "派发单不存在", 404)
    assignment, lead = row
    reveal_phone = assignment.status != AssignmentStatus.PENDING_CLAIM.value
    return ok(request, _assignment_dict(assignment, lead, reveal_phone=reveal_phone))


@router.post("/assignments/{assignment_id}/claim")
def claim_own_assignment(
    assignment_id: str,
    request: Request,
    principal=Depends(require_permissions("assignment.own.claim")),
    db: Session = Depends(get_db),
):
    company = require_active_company(db, principal.company_id)
    result = claim_assignment(
        db,
        assignment_id=assignment_id,
        company_id=company.id,
        claimed_by=principal.user_id,
    )
    lead = get_dispatch_lead(db, result.assignment.lead_id)
    write_audit(
        db,
        principal=principal,
        action="V12_ASSIGNMENT_CLAIM",
        resource_type="assignment",
        resource_id=result.assignment.id,
        company_id=company.id,
        after={
            "lead_id": lead.id,
            "status": result.assignment.status,
            "points": result.assignment.points_price,
            "ledger_id": result.ledger.id,
            "appeal_deadline_at": result.assignment.appeal_deadline_at.isoformat()
            if result.assignment.appeal_deadline_at
            else None,
            "reward_id": result.reward.id if result.reward else None,
            "idempotent": result.idempotent,
        },
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(
        request,
        {
            "assignment": _assignment_dict(result.assignment, lead, reveal_phone=True),
            "ledger": {
                "id": result.ledger.id,
                "delta": result.ledger.delta,
                "balance_after": result.ledger.balance_after,
            },
            "reward": {
                "id": result.reward.id,
                "status": result.reward.status,
                "reward_points": result.reward.reward_points,
                "reward_due_at": result.reward.reward_due_at.isoformat() if result.reward.reward_due_at else None,
            }
            if result.reward
            else None,
            "idempotent": result.idempotent,
        },
        "领取成功" if not result.idempotent else "派发单已领取",
    )

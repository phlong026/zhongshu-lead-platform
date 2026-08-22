from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.auth import require_permissions
from ..core.database import get_db
from ..core.errors import AppError
from ..core.models import Assignment, Lead
from ..core.responses import ok, page
from ..core.security import decrypt_text, mask_phone
from ..core.v12_enums import LeadV12Status
from ..schemas.v12_dispatch import ManualDispatchBody
from ..services.audit import write_audit
from ..services.claim_singleflight import run_claim_singleflight
from ..services.dispatch_v12 import (
    CLAIMED_CONTACT_STATUSES,
    candidate_to_dict,
    claim_assignment,
    dispatch_manually_with_outcome,
    get_dispatch_lead,
    lead_pool_item,
    list_candidates,
    list_dispatch_pool,
    manual_dispatch_idempotency_guard,
)

router = APIRouter(prefix="/v1.2", tags=["v1.2-dispatch-claim"])


def _principal_company_id(principal) -> str:
    if not principal.company_id:
        raise AppError("COMPANY_REQUIRED", "当前账号未绑定公司", 403)
    return principal.company_id


@lru_cache(maxsize=4096)
def _masked_encrypted_phone(phone_encrypted: str) -> str:
    return mask_phone(decrypt_text(phone_encrypted))


def _assignment_dict(assignment: Assignment, lead: Lead, *, reveal_phone: bool = False) -> dict:
    phone = decrypt_text(lead.phone_encrypted) if reveal_phone else None
    phone_masked = mask_phone(phone) if phone is not None else _masked_encrypted_phone(lead.phone_encrypted)
    return {
        "id": assignment.id,
        "lead_id": assignment.lead_id,
        "company_id": assignment.company_id,
        "supplier_company_id": assignment.supplier_company_id,
        "receiver_company_id": assignment.receiver_company_id,
        "status": assignment.status,
        "lead_status": lead.status,
        "current_follow_status": lead.current_follow_status,
        "points_price": assignment.points_price,
        "claim_points": assignment.claim_points,
        "price_rule_id": assignment.price_rule_id,
        "price_version": assignment.price_version,
        "customer_name": lead.customer_name,
        "phone": phone,
        "phone_masked": phone_masked,
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


def _assignment_detail_projection(assignment_id: str, company_id: str):
    return (
        select(
            Assignment.id,
            Assignment.lead_id,
            Assignment.company_id,
            Assignment.supplier_company_id,
            Assignment.receiver_company_id,
            Assignment.status,
            Assignment.points_price,
            Assignment.claim_points,
            Assignment.price_rule_id,
            Assignment.price_version,
            Assignment.assigned_at,
            Assignment.expires_at,
            Assignment.claimed_at,
            Assignment.appeal_deadline_at,
            Assignment.reward_due_at,
            Assignment.first_followup_due_at,
            Lead.customer_name,
            Lead.phone_encrypted,
            Lead.city,
            Lead.district,
            Lead.region_code,
            Lead.need_summary,
            Lead.status.label("lead_status"),
            Lead.current_follow_status,
        )
        .join(Lead, Lead.id == Assignment.lead_id)
        .where(Assignment.id == assignment_id, Assignment.company_id == company_id)
    )


def _projected_assignment_dict(row, *, reveal_phone: bool = False) -> dict:
    phone = decrypt_text(row.phone_encrypted) if reveal_phone else None
    phone_masked = mask_phone(phone) if phone is not None else _masked_encrypted_phone(row.phone_encrypted)
    return {
        "id": row.id,
        "lead_id": row.lead_id,
        "company_id": row.company_id,
        "supplier_company_id": row.supplier_company_id,
        "receiver_company_id": row.receiver_company_id,
        "status": row.status,
        "lead_status": row.lead_status,
        "current_follow_status": row.current_follow_status,
        "points_price": row.points_price,
        "claim_points": row.claim_points,
        "price_rule_id": row.price_rule_id,
        "price_version": row.price_version,
        "customer_name": row.customer_name,
        "phone": phone,
        "phone_masked": phone_masked,
        "city": row.city,
        "district": row.district,
        "region_code": row.region_code,
        "need_summary": row.need_summary,
        "assigned_at": row.assigned_at.isoformat(),
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "claimed_at": row.claimed_at.isoformat() if row.claimed_at else None,
        "appeal_deadline_at": row.appeal_deadline_at.isoformat() if row.appeal_deadline_at else None,
        "reward_due_at": row.reward_due_at.isoformat() if row.reward_due_at else None,
        "first_followup_due_at": row.first_followup_due_at.isoformat() if row.first_followup_due_at else None,
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
    if lead.status != LeadV12Status.READY_DISPATCH.value or lead.current_assignment_id:
        raise AppError(
            "LEAD_NOT_READY_DISPATCH",
            "客资当前不在待派发池",
            409,
            {"status": lead.status, "current_assignment_id": lead.current_assignment_id},
        )
    items = list_candidates(db, lead=lead)
    include_financials = principal.can("points.read") or principal.can("*")
    return ok(
        request,
        {
            "lead": lead_pool_item(lead),
            "eligible_count": sum(1 for item in items if item.eligible),
            "candidates": [candidate_to_dict(item, include_financials=include_financials) for item in items],
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
    with manual_dispatch_idempotency_guard(body.idempotency_key):
        outcome = dispatch_manually_with_outcome(
            db,
            lead_id=lead_id,
            company_id=body.company_id,
            assigned_by=principal.user_id,
            idempotency_key=body.idempotency_key,
            note=body.note,
        )
        assignment = outcome.assignment
        lead = get_dispatch_lead(db, lead_id)
        if outcome.created:
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
    company_id = _principal_company_id(principal)
    filters = [Assignment.company_id == company_id]
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
            reveal_phone=assignment.status in CLAIMED_CONTACT_STATUSES,
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
    company_id = _principal_company_id(principal)
    row = db.execute(_assignment_detail_projection(assignment_id, company_id)).one_or_none()
    if row is None:
        raise AppError("ASSIGNMENT_NOT_FOUND", "派发单不存在", 404)
    return ok(
        request,
        _projected_assignment_dict(
            row,
            reveal_phone=row.status in CLAIMED_CONTACT_STATUSES,
        ),
    )


@router.post("/assignments/{assignment_id}/claim")
def claim_own_assignment(
    assignment_id: str,
    request: Request,
    principal=Depends(require_permissions("assignment.own.claim")),
    db: Session = Depends(get_db),
):
    company_id = _principal_company_id(principal)

    def execute_claim() -> dict:
        result = claim_assignment(
            db,
            assignment_id=assignment_id,
            company_id=company_id,
            claimed_by=principal.user_id,
        )
        lead = get_dispatch_lead(db, result.assignment.lead_id)
        if not result.idempotent:
            write_audit(
                db,
                principal=principal,
                action="V12_ASSIGNMENT_CLAIM",
                resource_type="assignment",
                resource_id=result.assignment.id,
                company_id=company_id,
                after={
                    "lead_id": lead.id,
                    "status": result.assignment.status,
                    "points": result.assignment.points_price,
                    "ledger_id": result.ledger.id,
                    "appeal_deadline_at": result.assignment.appeal_deadline_at.isoformat()
                    if result.assignment.appeal_deadline_at
                    else None,
                    "reward_id": result.reward.id if result.reward else None,
                    "idempotent": False,
                },
                request_id=request.state.request_id,
            )
        db.commit()
        return {
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
                "reward_due_at": result.reward.reward_due_at.isoformat()
                if result.reward.reward_due_at
                else None,
            }
            if result.reward
            else None,
            "idempotent": result.idempotent,
        }

    payload, coalesced = run_claim_singleflight(
        f"{company_id}:{assignment_id}",
        execute_claim,
        before_wait=db.rollback,
    )
    if coalesced:
        payload["idempotent"] = True
    return ok(request, payload, "派发单已领取" if payload["idempotent"] else "领取成功")

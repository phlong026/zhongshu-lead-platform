from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.auth import CurrentPrincipal, require_permissions
from ..core.database import get_db
from ..core.errors import AppError
from ..core.models import Assignment
from ..core.responses import ok
from ..schemas.claim import ClaimBody
from ..services.audit import write_audit
from ..services.claim_service import claim_assignment, own_assignment_detail, run_assignment_timeouts
from ..services.deeplink import decode_assignment_link_token
from ..services.points_service import ledger_to_dict

router = APIRouter(prefix="/claims", tags=["claims"])


@router.post("/assignments/{assignment_id}")
def claim(assignment_id: str, body: ClaimBody, request: Request, principal=Depends(require_permissions("assignment.own.claim")), db: Session = Depends(get_db)):
    assignment, ledger = claim_assignment(db, assignment_id, principal, body.idempotency_key)
    write_audit(db, principal=principal, action="ASSIGNMENT_CLAIM", resource_type="assignment", resource_id=assignment.id, company_id=assignment.company_id, after={"status": assignment.status, "ledger_id": ledger.id}, request_id=request.state.request_id)
    db.commit()
    return ok(request, {"assignment": own_assignment_detail(db, assignment, principal), "ledger": ledger_to_dict(ledger)}, "领取成功")


@router.get("/assignments/{assignment_id}")
def own_detail(assignment_id: str, request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)):
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise AppError("ASSIGNMENT_NOT_FOUND", "派发订单不存在", 404)
    return ok(request, own_assignment_detail(db, assignment, principal))


@router.get("/resolve-link")
def resolve_link(token: str, request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)):
    payload = decode_assignment_link_token(token)
    if payload.get("company_id") != principal.company_id:
        raise AppError("FORBIDDEN", "链接不属于当前加盟商", 403)
    assignment = db.get(Assignment, payload["sub"])
    if not assignment or assignment.company_id != principal.company_id:
        raise AppError("ASSIGNMENT_NOT_FOUND", "客资已失效", 404)
    return ok(request, {"assignment_id": assignment.id, "status": assignment.status, "route": f"/leads/{assignment.id}"})


@router.post("/jobs/assignment-timeouts")
def run_timeouts(request: Request, principal=Depends(require_permissions("*")), db: Session = Depends(get_db)):
    result = run_assignment_timeouts(db)
    write_audit(db, principal=principal, action="JOB_ASSIGNMENT_TIMEOUT", resource_type="job", after=result, request_id=request.state.request_id)
    db.commit()
    return ok(request, result)

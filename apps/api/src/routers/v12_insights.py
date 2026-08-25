from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core import models_v12 as _models_v12  # noqa: F401
from ..core import reward_models_v12 as _reward_models_v12  # noqa: F401
from ..core.auth import CurrentPrincipal, require_permissions
from ..core.database import get_db
from ..core.errors import AppError
from ..core.models import (
    Assignment,
    AuditLog,
    Company,
    FollowUp,
    Lead,
    Notification,
    NotificationOutbox,
    PointsLedger,
    ReturnRequest,
    User,
    VerificationTask,
)
from ..core.models_v12 import SupplierLeadReward
from ..core.responses import ok, page
from ..core.security import decrypt_text, mask_phone
from ..services.return_v12 import return_request_to_dict
from ..services.storage import create_file_access_token

router = APIRouter(prefix="/v1.2", tags=["v1.2-reports-audit"])


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _time(column, start: datetime | None, end: datetime | None) -> list[Any]:
    return ([column >= start] if start else []) + ([column <= end] if end else [])


def _counts(db: Session, model, filters: list[Any]) -> dict[str, int]:
    rows = db.execute(select(model.status, func.count(model.id)).where(*filters).group_by(model.status)).all()
    return {str(status): int(count) for status, count in rows}


def _summary(db: Session, model, filters: list[Any]) -> dict[str, Any]:
    return {
        "total": int(db.scalar(select(func.count(model.id)).where(*filters)) or 0),
        "by_status": _counts(db, model, filters),
    }


@router.get("/reports/overview")
def overview(
    request: Request,
    principal=Depends(require_permissions("report.v12.read")),
    db: Session = Depends(get_db),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    company_id: str | None = Query(default=None),
):
    lead_f = [Lead.source_kind.is_not(None), *_time(Lead.created_at, created_from, created_to)]
    assignment_f = _time(Assignment.created_at, created_from, created_to)
    return_f = _time(ReturnRequest.created_at, created_from, created_to)
    reward_f = _time(SupplierLeadReward.created_at, created_from, created_to)
    points_f = [PointsLedger.business_type.like("V12_%"), *_time(PointsLedger.created_at, created_from, created_to)]
    if company_id:
        lead_f.append(Lead.supplier_company_id == company_id)
        assignment_f.append(or_(Assignment.company_id == company_id, Assignment.receiver_company_id == company_id, Assignment.supplier_company_id == company_id))
        return_f.append(ReturnRequest.company_id == company_id)
        reward_f.append(or_(SupplierLeadReward.supplier_company_id == company_id, SupplierLeadReward.receiver_company_id == company_id))
        points_f.append(PointsLedger.company_id == company_id)
    rewards = _summary(db, SupplierLeadReward, reward_f)
    rewards["points"] = int(db.scalar(select(func.coalesce(func.sum(SupplierLeadReward.reward_points), 0)).where(*reward_f)) or 0)
    data = {
        "scope": {"company_id": company_id, "created_from": _iso(created_from), "created_to": _iso(created_to)},
        "leads": _summary(db, Lead, lead_f),
        "assignments": _summary(db, Assignment, assignment_f),
        "returns": _summary(db, ReturnRequest, return_f),
        "supplier_rewards": rewards,
    }
    if any(principal.can(code) for code in ("*", "points.read", "dashboard.finance.read")):
        points = db.execute(
            select(func.count(PointsLedger.id), func.coalesce(func.sum(PointsLedger.delta), 0)).where(*points_f)
        ).one()
        data["points_ledger"] = {"count": int(points[0]), "net_delta": int(points[1])}
    return ok(request, data)


@router.get("/reports/own")
def own_report(request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)):
    if not principal.company_id:
        raise AppError("COMPANY_CONTEXT_REQUIRED", "当前账号未绑定公司", 403)
    if not any(principal.can(code) for code in ("*", "assignment.own.read", "assignment.employee.read", "supplier.lead.manage", "supplier.reward.own.read", "points.own.read")):
        raise AppError("FORBIDDEN", "无权查看公司业务报表", 403)
    company_id = principal.company_id
    employee_scope = principal.has_any_role("FRANCHISE_EMPLOYEE") and principal.can("assignment.employee.read")
    if employee_scope:
        assignment_ids = select(Assignment.id).where(
            Assignment.company_id == company_id,
            Assignment.internal_assignee_user_id == principal.user_id,
        )
        lead_f = [
            Lead.supplier_company_id == company_id,
            Lead.submitter_user_id == principal.user_id,
        ]
        assignment_f = [
            Assignment.company_id == company_id,
            Assignment.internal_assignee_user_id == principal.user_id,
        ]
        return_f = [
            ReturnRequest.company_id == company_id,
            ReturnRequest.assignment_id.in_(assignment_ids),
        ]
        rewards = {"total": 0, "by_status": {}, "points": 0}
    else:
        lead_f = [Lead.supplier_company_id == company_id]
        assignment_f = [or_(Assignment.company_id == company_id, Assignment.receiver_company_id == company_id)]
        return_f = [ReturnRequest.company_id == company_id]
        reward_f = [SupplierLeadReward.supplier_company_id == company_id]
        rewards = _summary(db, SupplierLeadReward, reward_f)
        rewards["points"] = int(
            db.scalar(select(func.coalesce(func.sum(SupplierLeadReward.reward_points), 0)).where(*reward_f)) or 0
        )
    unread = db.scalar(select(func.count(Notification.id)).where(
        or_(Notification.user_id == principal.user_id, (Notification.user_id.is_(None)) & (Notification.company_id == company_id)),
        Notification.read_at.is_(None),
    )) or 0
    return ok(request, {
        "company_id": company_id,
        "supplier_leads": _summary(db, Lead, lead_f),
        "received_assignments": _summary(db, Assignment, assignment_f),
        "returns": _summary(db, ReturnRequest, return_f),
        "supplier_rewards": rewards,
        "unread_notifications": int(unread),
    })


def _audit(item: AuditLog, *, actor_name: str | None = None) -> dict[str, Any]:
    return {
        "id": item.id, "request_id": item.request_id, "actor_user_id": item.actor_user_id,
        "actor_name": actor_name or "系统自动处理",
        "actor_role_codes": list(item.actor_role_codes or []), "action": item.action,
        "resource_type": item.resource_type, "resource_id": item.resource_id,
        "company_id": item.company_id, "before": item.before_json, "after": item.after_json,
        "metadata": item.metadata_json, "created_at": item.created_at.isoformat(),
    }


def _related_ids(db: Session, lead_id: str | None, assignment_id: str | None, return_id: str | None, reward_id: str | None) -> set[str]:
    ids = {value for value in (lead_id, assignment_id, return_id, reward_id) if value}
    assignment = db.get(Assignment, assignment_id) if assignment_id else None
    return_request = db.get(ReturnRequest, return_id) if return_id else None
    reward = db.get(SupplierLeadReward, reward_id) if reward_id else None
    if assignment:
        ids.add(assignment.lead_id)
    if return_request:
        ids.update({return_request.lead_id, return_request.assignment_id})
        if return_request.verification_task_id:
            ids.add(return_request.verification_task_id)
    if reward:
        ids.update({reward.lead_id, reward.assignment_id})
        ids.update(value for value in (reward.ledger_id, reward.reversal_ledger_id) if value)
    return ids


@router.get("/audit-events")
def audit_events(
    request: Request,
    _principal=Depends(require_permissions("audit.read")),
    db: Session = Depends(get_db),
    business_id: str | None = None, lead_id: str | None = None, assignment_id: str | None = None,
    return_id: str | None = None, reward_id: str | None = None, action: str | None = None,
    company_id: str | None = None, request_id: str | None = None,
    created_from: datetime | None = None, created_to: datetime | None = None,
    page_no: int = Query(default=1, alias="page", ge=1), page_size: int = Query(default=50, ge=1, le=200),
):
    ids = _related_ids(db, lead_id, assignment_id, return_id, reward_id)
    if business_id:
        ids.add(business_id)
    filters: list[Any] = []
    if ids:
        filters.append(or_(AuditLog.resource_id.in_(ids), AuditLog.request_id.in_(ids)))
    if action:
        filters.append(AuditLog.action == action.strip().upper())
    if company_id:
        filters.append(AuditLog.company_id == company_id)
    if request_id:
        filters.append(AuditLog.request_id == request_id)
    filters += _time(AuditLog.created_at, created_from, created_to)
    total = int(db.scalar(select(func.count(AuditLog.id)).where(*filters)) or 0)
    items = db.scalars(select(AuditLog).where(*filters).order_by(AuditLog.created_at.desc()).offset((page_no - 1) * page_size).limit(page_size)).all()
    return ok(request, page([_audit(item) for item in items], total, page_no, page_size))


def _display_name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.display_name or user.username


def _trace(db: Session, business_id: str, *, evidence_user_id: str | None = None) -> dict[str, Any]:
    lead = db.get(Lead, business_id)
    assignment = db.get(Assignment, business_id)
    return_request = db.get(ReturnRequest, business_id)
    reward = db.get(SupplierLeadReward, business_id)
    task = db.get(VerificationTask, business_id)
    lead_id = lead.id if lead else assignment.lead_id if assignment else return_request.lead_id if return_request else reward.lead_id if reward else task.lead_id if task else None
    assignment_id = assignment.id if assignment else return_request.assignment_id if return_request else reward.assignment_id if reward else getattr(task, "assignment_id", None) if task else None
    assignments = db.scalars(select(Assignment).where(Assignment.lead_id == lead_id).order_by(Assignment.created_at)).all() if lead_id else []
    assignment_ids = {item.id for item in assignments}
    if assignment_id:
        assignment_ids.add(assignment_id)
    relation_filter = lambda model: or_(model.lead_id == lead_id, model.assignment_id.in_(assignment_ids))
    returns = db.scalars(select(ReturnRequest).where(relation_filter(ReturnRequest)).order_by(ReturnRequest.created_at)).all() if lead_id or assignment_ids else []
    rewards = db.scalars(select(SupplierLeadReward).where(relation_filter(SupplierLeadReward)).order_by(SupplierLeadReward.created_at)).all() if lead_id or assignment_ids else []
    tasks = db.scalars(select(VerificationTask).where(relation_filter(VerificationTask)).order_by(VerificationTask.created_at)).all() if lead_id or assignment_ids else []
    ids = {business_id, *assignment_ids, *(item.id for item in returns), *(item.id for item in rewards), *(item.id for item in tasks)}
    if lead_id:
        ids.add(lead_id)
    for item in rewards:
        ids.update(value for value in (item.ledger_id, item.reversal_ledger_id) if value)
    followups = db.scalars(
        select(FollowUp).where(FollowUp.assignment_id.in_(assignment_ids)).order_by(FollowUp.created_at)
    ).all() if assignment_ids else []
    ledgers = db.scalars(
        select(PointsLedger)
        .where(or_(PointsLedger.business_id.in_(ids), PointsLedger.id.in_(ids)))
        .order_by(PointsLedger.created_at)
    ).all() if ids else []
    audits = db.scalars(select(AuditLog).where(or_(AuditLog.resource_id.in_(ids), AuditLog.request_id == business_id)).order_by(AuditLog.created_at)).all()
    outboxes = db.scalars(select(NotificationOutbox).where(NotificationOutbox.aggregate_id.in_(ids)).order_by(NotificationOutbox.created_at)).all()
    notification_ids = {str(item.payload.get("notification_id")) for item in outboxes if item.payload.get("notification_id")}
    notifications = db.scalars(select(Notification).where(Notification.id.in_(notification_ids)).order_by(Notification.created_at)).all() if notification_ids else []
    resolved_lead = db.get(Lead, lead_id) if lead_id else None
    user_ids = {
        value
        for value in (
            resolved_lead.submitter_user_id if resolved_lead else None,
            *(item.assigned_by for item in assignments),
            *(item.internal_assignee_user_id for item in assignments),
            *(item.submitted_by for item in returns),
            *(item.reviewed_by for item in returns),
            *(item.assignee_user_id for item in tasks),
            *(item.created_by for item in followups),
            *(item.created_by for item in ledgers),
            *(item.actor_user_id for item in audits),
        )
        if value
    }
    users = {
        item.id: item
        for item in db.scalars(select(User).where(User.id.in_(user_ids))).all()
    } if user_ids else {}
    company_ids = {
        value
        for value in (
            resolved_lead.supplier_company_id if resolved_lead else None,
            *(item.company_id for item in assignments),
            *(item.supplier_company_id for item in assignments),
            *(item.receiver_company_id for item in assignments),
            *(item.company_id for item in returns),
            *(item.supplier_company_id for item in rewards),
            *(item.receiver_company_id for item in rewards),
            *(item.company_id for item in ledgers),
        )
        if value
    }
    companies = {
        item.id: item
        for item in db.scalars(select(Company).where(Company.id.in_(company_ids))).all()
    } if company_ids else {}
    audit_events = [_audit(item, actor_name=_display_name(users.get(item.actor_user_id))) for item in audits]
    timeline = [
        {
            "at": item["created_at"],
            "kind": "AUDIT",
            "id": item["id"],
            "action": item["action"],
            "resource_type": item["resource_type"],
            "resource_id": item["resource_id"],
            "actor_name": item["actor_name"],
            "summary": str((item["metadata"] or {}).get("reason") or "已完成本次处理"),
        }
        for item in audit_events
    ]
    timeline += [
        {
            "at": item.created_at.isoformat(),
            "kind": "NOTIFICATION",
            "id": item.id,
            "action": item.scene,
            "resource_type": "notification",
            "resource_id": item.id,
            "status": item.status,
            "summary": item.title,
        }
        for item in notifications
    ]
    timeline.sort(key=lambda item: (item["at"], item["kind"], item["id"]))
    trace_returns = []
    for item in returns:
        data = return_request_to_dict(db, item, include_evidence=True)
        data["company_name"] = companies.get(item.company_id).name if item.company_id in companies else None
        data["submitted_by_name"] = _display_name(users.get(item.submitted_by))
        data["reviewed_by_name"] = _display_name(users.get(item.reviewed_by))
        if evidence_user_id:
            for evidence in data.get("evidences", []):
                evidence["access_token"] = create_file_access_token(evidence["id"], evidence_user_id)
        trace_returns.append(data)
    return {
        "business_id": business_id, "linked_ids": sorted(ids),
        "lead": {
            "id": resolved_lead.id,
            "customer_name": resolved_lead.customer_name,
            "phone_masked": mask_phone(decrypt_text(resolved_lead.phone_encrypted)),
            "status": resolved_lead.status,
            "source_kind": resolved_lead.source_kind,
            "source_channel": resolved_lead.source_channel,
            "review_status": resolved_lead.review_status,
            "review_note": resolved_lead.review_note,
            "duplicate_status": resolved_lead.duplicate_status,
            "city": resolved_lead.city,
            "district": resolved_lead.district,
            "need_summary": resolved_lead.need_summary,
            "submitted_at": _iso(resolved_lead.submitted_at),
            "created_at": _iso(resolved_lead.created_at),
            "supplier_company_id": resolved_lead.supplier_company_id,
            "supplier_company_name": companies.get(resolved_lead.supplier_company_id).name if resolved_lead.supplier_company_id in companies else None,
            "submitter_name": _display_name(users.get(resolved_lead.submitter_user_id)),
        } if resolved_lead else None,
        "assignments": [{
            "id": item.id, "lead_id": item.lead_id, "company_id": item.company_id,
            "company_name": companies.get(item.company_id).name if item.company_id in companies else None,
            "supplier_company_id": item.supplier_company_id,
            "supplier_company_name": companies.get(item.supplier_company_id).name if item.supplier_company_id in companies else None,
            "receiver_company_id": item.receiver_company_id,
            "receiver_company_name": companies.get(item.receiver_company_id).name if item.receiver_company_id in companies else None,
            "status": item.status, "current_follow_status": resolved_lead.current_follow_status if resolved_lead else None,
            "points_price": item.points_price, "claim_points": item.claim_points,
            "assigned_at": _iso(item.assigned_at), "claimed_at": _iso(item.claimed_at),
            "assigned_by_name": _display_name(users.get(item.assigned_by)),
            "internal_assignee_name": _display_name(users.get(item.internal_assignee_user_id)),
        } for item in assignments],
        "returns": trace_returns,
        "supplier_rewards": [{
            "id": item.id, "assignment_id": item.assignment_id, "lead_id": item.lead_id,
            "supplier_company_id": item.supplier_company_id,
            "supplier_company_name": companies.get(item.supplier_company_id).name if item.supplier_company_id in companies else None,
            "receiver_company_id": item.receiver_company_id,
            "receiver_company_name": companies.get(item.receiver_company_id).name if item.receiver_company_id in companies else None,
            "status": item.status, "claim_points": int(item.claim_points), "reward_points": int(item.reward_points),
            "reward_due_at": _iso(item.reward_due_at), "settled_at": _iso(item.settled_at),
            "ledger_id": item.ledger_id, "reversal_ledger_id": item.reversal_ledger_id,
            "exception_reason": item.exception_reason,
        } for item in rewards],
        "verification_tasks": [{
            "id": item.id, "lead_id": item.lead_id, "assignment_id": item.assignment_id,
            "return_request_id": item.return_request_id, "task_type": item.task_type,
            "status": item.status, "assignee_user_id": item.assignee_user_id,
            "assignee_name": _display_name(users.get(item.assignee_user_id)),
            "contact_result": item.contact_result, "conclusion": item.verification_conclusion,
            "created_at": _iso(item.created_at), "assigned_at": _iso(item.assigned_at),
            "started_at": _iso(item.started_at), "submitted_at": _iso(item.submitted_at),
        } for item in tasks],
        "followups": [{
            "id": item.id, "assignment_id": item.assignment_id, "status": item.status,
            "note": item.note, "next_followup_at": _iso(item.next_followup_at),
            "created_at": _iso(item.created_at), "created_by_name": _display_name(users.get(item.created_by)),
        } for item in followups],
        "points_ledgers": [{
            "id": item.id, "company_id": item.company_id,
            "company_name": companies.get(item.company_id).name if item.company_id in companies else None,
            "ledger_type": item.ledger_type, "delta": int(item.delta), "balance_after": int(item.balance_after),
            "business_type": item.business_type, "business_id": item.business_id,
            "created_at": _iso(item.created_at), "created_by_name": _display_name(users.get(item.created_by)),
        } for item in ledgers],
        "notifications": [{"id": item.id, "scene": item.scene, "title": item.title, "deep_link": item.deep_link, "status": item.status, "read_at": _iso(item.read_at), "created_at": _iso(item.created_at)} for item in notifications],
        "audit_events": audit_events, "timeline": timeline,
    }


@router.get("/trace/{business_id}")
def business_trace(business_id: str, request: Request, principal=Depends(require_permissions("audit.read")), db: Session = Depends(get_db)):
    data = _trace(db, business_id, evidence_user_id=principal.user_id)
    if len(data["linked_ids"]) == 1 and not data["audit_events"] and not data["notifications"] and data["lead"] is None:
        raise AppError("BUSINESS_TRACE_NOT_FOUND", "未找到该业务 ID", 404)
    return ok(request, data)

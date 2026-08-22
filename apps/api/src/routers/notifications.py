from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.auth import CurrentPrincipal, require_permissions
from ..core.database import get_db
from ..core.errors import AppError
from ..core.models import Notification, NotificationOutbox
from ..core.responses import ok, page
from ..core.security import scrub_credentials
from ..integrations.wechat import WechatOfficialAccountClient
from ..services.audit import write_audit
from ..services.outbox_worker import process_outbox

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/gate0")
def gate0(request: Request, principal=Depends(require_permissions("*"))):
    return ok(request, WechatOfficialAccountClient().gate0_diagnostics())


@router.get("")
def list_notifications(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    unread_only: bool = Query(default=False),
    page_no: int = Query(default=1, alias="page", ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    stmt = select(Notification).where((Notification.user_id == principal.user_id) | ((Notification.user_id.is_(None)) & (Notification.company_id == principal.company_id)))
    count_stmt = select(func.count(Notification.id)).where((Notification.user_id == principal.user_id) | ((Notification.user_id.is_(None)) & (Notification.company_id == principal.company_id)))
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
        count_stmt = count_stmt.where(Notification.read_at.is_(None))
    total = db.scalar(count_stmt) or 0
    items = db.scalars(stmt.order_by(Notification.created_at.desc()).offset((page_no - 1) * page_size).limit(page_size)).all()
    return ok(request, page([{"id": x.id, "scene": x.scene, "title": x.title, "body": x.body, "deep_link": x.deep_link, "status": x.status, "read_at": x.read_at.isoformat() if x.read_at else None, "created_at": x.created_at.isoformat()} for x in items], total, page_no, page_size))


@router.post("/{notification_id}/read")
def mark_read(notification_id: str, request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)):
    item = db.get(Notification, notification_id)
    if not item or (item.user_id not in {None, principal.user_id}) or (item.company_id and item.company_id != principal.company_id):
        raise AppError("NOTIFICATION_NOT_FOUND", "消息不存在", 404)
    item.read_at = datetime.now(timezone.utc)
    db.commit()
    return ok(request)


@router.get("/outbox/failed")
def failed_outbox(request: Request, principal=Depends(require_permissions("notification.retry")), db: Session = Depends(get_db), status: str = Query(default="FAILED")):
    items = db.scalars(select(NotificationOutbox).where(NotificationOutbox.status == status).order_by(NotificationOutbox.created_at.desc()).limit(500)).all()
    # N3：存量脏 last_error（脱敏上线前落库）出参前同样打码兜底。
    return ok(request, [{"id": x.id, "event_type": x.event_type, "aggregate_id": x.aggregate_id, "attempts": x.attempts, "last_error": scrub_credentials(x.last_error), "next_attempt_at": x.next_attempt_at.isoformat() if x.next_attempt_at else None, "created_at": x.created_at.isoformat()} for x in items])


@router.post("/outbox/{outbox_id}/retry")
def retry_outbox(outbox_id: str, request: Request, principal=Depends(require_permissions("notification.retry")), db: Session = Depends(get_db)):
    item = db.get(NotificationOutbox, outbox_id)
    if not item:
        raise AppError("OUTBOX_NOT_FOUND", "通知任务不存在", 404)
    item.status = "PENDING"
    item.next_attempt_at = None
    item.last_error = None
    write_audit(db, principal=principal, action="NOTIFICATION_RETRY", resource_type="outbox", resource_id=item.id, request_id=request.state.request_id)
    db.commit()
    return ok(request)


@router.post("/jobs/process-outbox")
def process(request: Request, principal=Depends(require_permissions("*")), db: Session = Depends(get_db), limit: int = Query(default=100, ge=1, le=1000)):
    result = process_outbox(db, limit=limit)
    write_audit(db, principal=principal, action="JOB_PROCESS_OUTBOX", resource_type="job", after=result, request_id=request.state.request_id)
    db.commit()
    return ok(request, result)

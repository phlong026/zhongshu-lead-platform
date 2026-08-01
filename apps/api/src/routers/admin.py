from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.auth import CurrentPrincipal, require_permissions
from ..core.database import get_db
from ..core.enums import ConfigStatus
from ..core.errors import AppError
from ..core.models import AuditLog, SystemConfig
from ..core.responses import ok, page
from ..schemas.admin import SystemConfigCreateBody, SystemConfigPublishBody
from ..services.admin_service import dashboard_summary, dashboard_trends, operational_alerts, source_distribution
from ..services.audit import write_audit

router = APIRouter(tags=["admin"])


@router.get("/dashboard/summary")
def summary(request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)):
    if not any(
        principal.can(code)
        for code in [
            "dashboard.business.read",
            "dashboard.operation.read",
            "dashboard.telesales.read",
            "dashboard.finance.read",
            "h5.home",
            "*",
        ]
    ):
        raise AppError("FORBIDDEN", "无权查看数据看板", 403)
    return ok(request, dashboard_summary(db, principal))


@router.get("/dashboard/trends")
def trends(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    days: int = Query(default=7, ge=1, le=90),
):
    if principal.has_any_role("FRANCHISE_OWNER"):
        raise AppError("FORBIDDEN", "加盟商端不提供平台趋势", 403)
    if not any(principal.can(code) for code in ["dashboard.business.read", "dashboard.operation.read", "dashboard.finance.read", "*"]):
        raise AppError("FORBIDDEN", "无权查看趋势", 403)
    return ok(request, dashboard_trends(db, days=days))


@router.get("/dashboard/sources")
def sources(request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)):
    if principal.has_any_role("FRANCHISE_OWNER") or not any(
        principal.can(code) for code in ["dashboard.business.read", "dashboard.operation.read", "*"]
    ):
        raise AppError("FORBIDDEN", "无权查看来源分布", 403)
    return ok(request, source_distribution(db))


@router.get("/dashboard/alerts")
def alerts(request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)):
    if principal.has_any_role("FRANCHISE_OWNER"):
        raise AppError("FORBIDDEN", "无权查看平台预警", 403)
    return ok(request, operational_alerts(db))


@router.get("/system-configs")
def list_configs(
    request: Request,
    principal=Depends(require_permissions("*")),
    db: Session = Depends(get_db),
    domain: str | None = None,
    status: str | None = None,
):
    stmt = select(SystemConfig)
    if domain:
        stmt = stmt.where(SystemConfig.domain == domain)
    if status:
        stmt = stmt.where(SystemConfig.status == status)
    items = db.scalars(stmt.order_by(SystemConfig.domain, SystemConfig.key, SystemConfig.version.desc())).all()
    return ok(
        request,
        [
            {
                "id": x.id,
                "domain": x.domain,
                "key": x.key,
                "value": x.value_json,
                "version": x.version,
                "status": x.status,
                "effective_at": x.effective_at.isoformat() if x.effective_at else None,
                "updated_at": x.updated_at.isoformat(),
            }
            for x in items
        ],
    )


@router.post("/system-configs")
def create_config(
    body: SystemConfigCreateBody,
    request: Request,
    principal=Depends(require_permissions("*")),
    db: Session = Depends(get_db),
):
    latest = int(
        db.scalar(select(func.coalesce(func.max(SystemConfig.version), 0)).where(SystemConfig.domain == body.domain, SystemConfig.key == body.key))
        or 0
    )
    item = SystemConfig(
        domain=body.domain,
        key=body.key,
        value_json=body.value,
        version=latest + 1,
        status=ConfigStatus.PUBLISHED if body.publish_immediately else ConfigStatus.DRAFT,
        effective_at=datetime.now(timezone.utc) if body.publish_immediately else None,
        published_by=principal.user_id if body.publish_immediately else None,
    )
    if body.publish_immediately:
        prior = db.scalars(
            select(SystemConfig).where(
                SystemConfig.domain == body.domain,
                SystemConfig.key == body.key,
                SystemConfig.status == ConfigStatus.PUBLISHED,
            )
        ).all()
        for previous in prior:
            previous.status = ConfigStatus.RETIRED
    db.add(item)
    db.flush()
    write_audit(
        db,
        principal=principal,
        action="SYSTEM_CONFIG_CREATE",
        resource_type="system_config",
        resource_id=item.id,
        after={"domain": item.domain, "key": item.key, "version": item.version, "status": item.status},
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, {"id": item.id, "version": item.version, "status": item.status}, "配置已创建")


@router.post("/system-configs/{config_id}/publish")
def publish_config(
    config_id: str,
    body: SystemConfigPublishBody,
    request: Request,
    principal=Depends(require_permissions("*")),
    db: Session = Depends(get_db),
):
    item = db.get(SystemConfig, config_id)
    if not item:
        raise AppError("CONFIG_NOT_FOUND", "配置不存在", 404)
    if item.status == ConfigStatus.PUBLISHED:
        return ok(request, {"id": item.id, "status": item.status}, "配置已发布")
    prior = db.scalars(
        select(SystemConfig).where(
            SystemConfig.domain == item.domain,
            SystemConfig.key == item.key,
            SystemConfig.status == ConfigStatus.PUBLISHED,
        )
    ).all()
    for previous in prior:
        previous.status = ConfigStatus.RETIRED
    item.status = ConfigStatus.PUBLISHED
    item.effective_at = datetime.now(timezone.utc)
    item.published_by = principal.user_id
    write_audit(
        db,
        principal=principal,
        action="SYSTEM_CONFIG_PUBLISH",
        resource_type="system_config",
        resource_id=item.id,
        after={"domain": item.domain, "key": item.key, "version": item.version, "note": body.note},
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, {"id": item.id, "status": item.status, "effective_at": item.effective_at.isoformat()}, "配置已发布")


@router.get("/audit-logs")
def audit_logs(
    request: Request,
    principal=Depends(require_permissions("audit.read")),
    db: Session = Depends(get_db),
    action: str | None = None,
    resource_type: str | None = None,
    actor_user_id: str | None = None,
    page_no: int = Query(default=1, alias="page", ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    stmt = select(AuditLog)
    count_stmt = select(func.count(AuditLog.id))
    if action:
        stmt = stmt.where(AuditLog.action == action)
        count_stmt = count_stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
        count_stmt = count_stmt.where(AuditLog.resource_type == resource_type)
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
        count_stmt = count_stmt.where(AuditLog.actor_user_id == actor_user_id)
    total = int(db.scalar(count_stmt) or 0)
    items = db.scalars(stmt.order_by(AuditLog.created_at.desc()).offset((page_no - 1) * page_size).limit(page_size)).all()
    data = [
        {
            "id": x.id,
            "request_id": x.request_id,
            "actor_user_id": x.actor_user_id,
            "roles": x.actor_role_codes,
            "action": x.action,
            "resource_type": x.resource_type,
            "resource_id": x.resource_id,
            "company_id": x.company_id,
            "before": x.before_json,
            "after": x.after_json,
            "metadata": x.metadata_json,
            "ip_address": x.ip_address,
            "created_at": x.created_at.isoformat(),
        }
        for x in items
    ]
    return ok(request, page(data, total, page_no, page_size))

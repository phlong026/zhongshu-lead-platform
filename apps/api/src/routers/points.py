from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.auth import CurrentPrincipal, require_permissions
from ..core.database import get_db
from ..core.errors import AppError
from ..core.models import Company, LeadPriceRule, PointsAccount, PointsLedger, PointsPackage
from ..core.responses import ok, page
from ..schemas.points import ManualAdjustmentBody, PointsPackageBody, PriceRuleBody, RechargeBody, ReverseLedgerBody
from ..services.audit import write_audit
from ..services.points_service import (
    change_points,
    ledger_to_dict,
    points_available_for_dispatch,
    recharge_points,
    reverse_ledger,
)

router = APIRouter(prefix="/points", tags=["points"])


@router.get("/packages")
def list_packages(request: Request, db: Session = Depends(get_db), active_only: bool = Query(default=True)):
    stmt = select(PointsPackage)
    if active_only:
        stmt = stmt.where(PointsPackage.status == "PUBLISHED")
    items = db.scalars(stmt.order_by(PointsPackage.cash_amount_cents.asc(), PointsPackage.version.desc())).all()
    return ok(request, [{"id": x.id, "code": x.code, "name": x.name, "cash_amount_cents": x.cash_amount_cents, "base_points": x.base_points, "bonus_points": x.bonus_points, "level_code": x.level_code, "entitlements": x.entitlements_json, "version": x.version, "status": x.status} for x in items])


@router.post("/packages")
def create_package(body: PointsPackageBody, request: Request, principal=Depends(require_permissions("points.package.manage")), db: Session = Depends(get_db)):
    latest = db.scalar(select(func.max(PointsPackage.version)).where(PointsPackage.code == body.code)) or 0
    package = PointsPackage(
        code=body.code,
        name=body.name,
        cash_amount_cents=body.cash_amount_cents,
        base_points=body.base_points,
        bonus_points=body.bonus_points,
        level_code=body.level_code,
        entitlements_json=body.entitlements,
        version=latest + 1,
        status="PUBLISHED" if body.publish else "DRAFT",
        effective_at=body.effective_at or (datetime.now(timezone.utc) if body.publish else None),
        expires_at=body.expires_at,
    )
    db.add(package)
    db.flush()
    write_audit(db, principal=principal, action="POINTS_PACKAGE_CREATE", resource_type="points_package", resource_id=package.id, after={"code": package.code, "version": package.version}, request_id=request.state.request_id)
    db.commit()
    return ok(request, {"id": package.id, "version": package.version})


@router.get("/price-rules")
def list_price_rules(request: Request, principal=Depends(require_permissions("points.read")), db: Session = Depends(get_db)):
    items = db.scalars(select(LeadPriceRule).order_by(LeadPriceRule.priority, LeadPriceRule.version.desc())).all()
    return ok(request, [{"id": x.id, "region_code": x.region_code, "category_code": x.category_code, "brand_code": x.brand_code, "level_code": x.level_code, "points_cost": x.points_cost, "version": x.version, "priority": x.priority, "status": x.status} for x in items])


@router.post("/price-rules")
def create_price_rule(body: PriceRuleBody, request: Request, principal=Depends(require_permissions("points.package.manage")), db: Session = Depends(get_db)):
    latest = db.scalar(select(func.max(LeadPriceRule.version)).where(LeadPriceRule.region_code == body.region_code, LeadPriceRule.category_code == body.category_code, LeadPriceRule.brand_code == body.brand_code, LeadPriceRule.level_code == body.level_code)) or 0
    rule = LeadPriceRule(
        region_code=body.region_code,
        category_code=body.category_code,
        brand_code=body.brand_code,
        level_code=body.level_code,
        points_cost=body.points_cost,
        priority=body.priority,
        version=latest + 1,
        status="PUBLISHED" if body.publish else "DRAFT",
        effective_at=body.effective_at or (datetime.now(timezone.utc) if body.publish else None),
        expires_at=body.expires_at,
    )
    db.add(rule)
    db.flush()
    write_audit(db, principal=principal, action="POINTS_PRICE_RULE_CREATE", resource_type="lead_price_rule", resource_id=rule.id, after={"points_cost": rule.points_cost, "version": rule.version}, request_id=request.state.request_id)
    db.commit()
    return ok(request, {"id": rule.id, "version": rule.version})


@router.get("/accounts/{company_id}")
def get_account(company_id: str, request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)):
    if principal.company_id != company_id and not (principal.can("points.read") or principal.can("*")):
        raise AppError("FORBIDDEN", "无权查看积分账户", 403)
    company = db.get(Company, company_id)
    if not company:
        raise AppError("COMPANY_NOT_FOUND", "加盟商公司不存在", 404)
    balance, reserved, available = points_available_for_dispatch(db, company_id)
    return ok(request, {"company_id": company_id, "company_name": company.name, "level_code": company.level_code, "balance": balance, "pending_claim_points": reserved, "available_for_dispatch": available})


@router.get("/ledgers")
def list_ledgers(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    company_id: str | None = Query(default=None),
    ledger_type: str | None = Query(default=None),
    page_no: int = Query(default=1, alias="page", ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    if principal.has_any_role("FRANCHISE_OWNER"):
        company_id = principal.company_id
    elif not (principal.can("points.read") or principal.can("*")):
        raise AppError("FORBIDDEN", "无权查看积分流水", 403)
    stmt = select(PointsLedger)
    count_stmt = select(func.count(PointsLedger.id))
    if company_id:
        stmt = stmt.where(PointsLedger.company_id == company_id)
        count_stmt = count_stmt.where(PointsLedger.company_id == company_id)
    if ledger_type:
        stmt = stmt.where(PointsLedger.ledger_type == ledger_type)
        count_stmt = count_stmt.where(PointsLedger.ledger_type == ledger_type)
    total = db.scalar(count_stmt) or 0
    items = db.scalars(stmt.order_by(PointsLedger.created_at.desc()).offset((page_no - 1) * page_size).limit(page_size)).all()
    return ok(request, page([ledger_to_dict(x) for x in items], total, page_no, page_size))


@router.post("/recharge")
def recharge(body: RechargeBody, request: Request, principal=Depends(require_permissions("points.recharge")), db: Session = Depends(get_db)):
    package = db.get(PointsPackage, body.package_id)
    if not package:
        raise AppError("POINTS_PACKAGE_NOT_FOUND", "充值档位不存在", 404)
    ledger = recharge_points(db, company_id=body.company_id, package=package, cash_amount_cents=body.cash_amount_cents, external_reference=body.external_reference, idempotency_key=body.idempotency_key, created_by=principal.user_id, note=body.note)
    write_audit(db, principal=principal, action="POINTS_RECHARGE", resource_type="points_ledger", resource_id=ledger.id, company_id=body.company_id, after=ledger_to_dict(ledger), request_id=request.state.request_id)
    db.commit()
    return ok(request, ledger_to_dict(ledger), "充值积分成功")


@router.post("/adjust")
def adjust(body: ManualAdjustmentBody, request: Request, principal=Depends(require_permissions("points.recharge")), db: Session = Depends(get_db)):
    ledger = change_points(db, company_id=body.company_id, delta=body.delta, ledger_type="ADJUST", business_type="MANUAL_ADJUSTMENT", business_id=body.idempotency_key, idempotency_key=body.idempotency_key, created_by=principal.user_id, metadata={"reason": body.reason})
    write_audit(db, principal=principal, action="POINTS_ADJUST", resource_type="points_ledger", resource_id=ledger.id, company_id=body.company_id, after=ledger_to_dict(ledger), request_id=request.state.request_id)
    db.commit()
    return ok(request, ledger_to_dict(ledger))


@router.post("/ledgers/{ledger_id}/reverse")
def reverse(ledger_id: str, body: ReverseLedgerBody, request: Request, principal=Depends(require_permissions("points.reverse")), db: Session = Depends(get_db)):
    original = db.get(PointsLedger, ledger_id)
    if not original:
        raise AppError("POINTS_LEDGER_NOT_FOUND", "积分流水不存在", 404)
    reversal = reverse_ledger(db, original, reason=body.reason, idempotency_key=body.idempotency_key, created_by=principal.user_id)
    write_audit(db, principal=principal, action="POINTS_REVERSE", resource_type="points_ledger", resource_id=reversal.id, company_id=original.company_id, metadata={"original_ledger_id": original.id, "reason": body.reason}, request_id=request.state.request_id)
    db.commit()
    return ok(request, ledger_to_dict(reversal))

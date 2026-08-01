from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..core.enums import AssignmentStatus, PointsLedgerType
from ..core.errors import AppError
from ..core.models import Assignment, Company, Lead, LeadPriceRule, PointsAccount, PointsLedger, PointsPackage


def get_or_create_account(db: Session, company_id: str) -> PointsAccount:
    account = db.scalar(select(PointsAccount).where(PointsAccount.company_id == company_id))
    if account:
        return account
    if not db.get(Company, company_id):
        raise AppError("COMPANY_NOT_FOUND", "加盟商公司不存在", 404)
    account = PointsAccount(company_id=company_id, balance=0, version=1)
    db.add(account)
    db.flush()
    return account


def points_available_for_dispatch(db: Session, company_id: str) -> tuple[int, int, int]:
    account = get_or_create_account(db, company_id)
    reserved = db.scalar(
        select(func.coalesce(func.sum(Assignment.points_price), 0)).where(
            Assignment.company_id == company_id,
            Assignment.status == AssignmentStatus.PENDING_CLAIM,
        )
    ) or 0
    return int(account.balance), int(reserved), int(account.balance - reserved)


def resolve_price(db: Session, lead: Lead, company: Company) -> tuple[int, LeadPriceRule | None]:
    now = datetime.now(timezone.utc)
    rules = db.scalars(
        select(LeadPriceRule)
        .where(
            LeadPriceRule.status == "PUBLISHED",
            or_(LeadPriceRule.effective_at.is_(None), LeadPriceRule.effective_at <= now),
            or_(LeadPriceRule.expires_at.is_(None), LeadPriceRule.expires_at > now),
            or_(LeadPriceRule.region_code.is_(None), LeadPriceRule.region_code == lead.region_code),
            or_(LeadPriceRule.category_code.is_(None), LeadPriceRule.category_code == lead.category_code),
            or_(LeadPriceRule.brand_code.is_(None), LeadPriceRule.brand_code == lead.brand_code),
            or_(LeadPriceRule.level_code.is_(None), LeadPriceRule.level_code == company.level_code),
        )
        .order_by(
            LeadPriceRule.priority.asc(),
            LeadPriceRule.region_code.is_(None).asc(),
            LeadPriceRule.category_code.is_(None).asc(),
            LeadPriceRule.brand_code.is_(None).asc(),
            LeadPriceRule.level_code.is_(None).asc(),
            LeadPriceRule.version.desc(),
        )
    ).all()
    if rules:
        return rules[0].points_cost, rules[0]
    return 100, None


def change_points(
    db: Session,
    *,
    company_id: str,
    delta: int,
    ledger_type: str,
    business_type: str,
    business_id: str,
    idempotency_key: str,
    created_by: str | None,
    external_reference: str | None = None,
    related_ledger_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> PointsLedger:
    existing = db.scalar(
        select(PointsLedger).where(
            PointsLedger.company_id == company_id,
            PointsLedger.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return existing
    account = db.scalar(select(PointsAccount).where(PointsAccount.company_id == company_id).with_for_update())
    if not account:
        account = get_or_create_account(db, company_id)
    new_balance = int(account.balance) + int(delta)
    if new_balance < 0:
        raise AppError("POINTS_INSUFFICIENT", "积分不足", 409, {"balance": account.balance, "required": abs(delta)})
    account.balance = new_balance
    account.version += 1
    ledger = PointsLedger(
        account_id=account.id,
        company_id=company_id,
        ledger_type=ledger_type,
        delta=delta,
        balance_after=new_balance,
        business_type=business_type,
        business_id=business_id,
        idempotency_key=idempotency_key,
        external_reference=external_reference,
        related_ledger_id=related_ledger_id,
        metadata_json=metadata or {},
        created_by=created_by,
    )
    db.add(ledger)
    db.flush()
    return ledger


def recharge_points(
    db: Session,
    *,
    company_id: str,
    package: PointsPackage,
    cash_amount_cents: int,
    external_reference: str,
    idempotency_key: str,
    created_by: str,
    note: str | None,
) -> PointsLedger:
    duplicate_ref = db.scalar(select(PointsLedger).where(PointsLedger.external_reference == external_reference))
    if duplicate_ref:
        raise AppError("POINTS_EXTERNAL_REFERENCE_EXISTS", "该付款流水号已使用", 409)
    if package.status != "PUBLISHED":
        raise AppError("POINTS_PACKAGE_INACTIVE", "充值档位不可用", 409)
    if cash_amount_cents != package.cash_amount_cents:
        raise AppError("POINTS_CASH_AMOUNT_MISMATCH", "实收金额与档位不一致", 422)
    total = package.base_points + package.bonus_points
    company = db.get(Company, company_id)
    if not company:
        raise AppError("COMPANY_NOT_FOUND", "加盟商公司不存在", 404)
    company.level_code = package.level_code
    return change_points(
        db,
        company_id=company_id,
        delta=total,
        ledger_type=PointsLedgerType.RECHARGE,
        business_type="POINTS_PACKAGE",
        business_id=package.id,
        idempotency_key=idempotency_key,
        external_reference=external_reference,
        created_by=created_by,
        metadata={
            "package_code": package.code,
            "package_version": package.version,
            "cash_amount_cents": cash_amount_cents,
            "base_points": package.base_points,
            "bonus_points": package.bonus_points,
            "note": note,
        },
    )


def reverse_ledger(db: Session, original: PointsLedger, *, reason: str, idempotency_key: str, created_by: str) -> PointsLedger:
    existing_reversal = db.scalar(select(PointsLedger).where(PointsLedger.related_ledger_id == original.id, PointsLedger.ledger_type == PointsLedgerType.REVERSAL))
    if existing_reversal:
        raise AppError("POINTS_ALREADY_REVERSED", "该流水已经冲正", 409)
    return change_points(
        db,
        company_id=original.company_id,
        delta=-original.delta,
        ledger_type=PointsLedgerType.REVERSAL,
        business_type="LEDGER_REVERSAL",
        business_id=original.id,
        idempotency_key=idempotency_key,
        related_ledger_id=original.id,
        created_by=created_by,
        metadata={"reason": reason},
    )


def ledger_to_dict(ledger: PointsLedger) -> dict[str, Any]:
    return {
        "id": ledger.id,
        "company_id": ledger.company_id,
        "type": ledger.ledger_type,
        "delta": ledger.delta,
        "balance_after": ledger.balance_after,
        "business_type": ledger.business_type,
        "business_id": ledger.business_id,
        "external_reference": ledger.external_reference,
        "related_ledger_id": ledger.related_ledger_id,
        "metadata": ledger.metadata_json,
        "created_at": ledger.created_at.isoformat(),
    }

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..core.models import Company, Region
from ..core.models_v12 import CompanyLeadCapability, CompanyServiceAreaV12
from ..core.v12_enums import CompanyLeadCapabilityCode


VALID_CAPABILITIES = {item.value for item in CompanyLeadCapabilityCode}
VALID_REVIEW_STATUSES = {"PENDING", "APPROVED", "REJECTED"}


def require_active_company(db: Session, company_id: str | None) -> Company:
    if not company_id:
        raise AppError("COMPANY_REQUIRED", "当前账号未绑定公司", 403)
    company = db.get(Company, company_id)
    if not company or company.status != "ACTIVE":
        raise AppError("COMPANY_INACTIVE", "公司不存在或已停用", 403)
    return company


def has_lead_capability(db: Session, company_id: str, capability_code: str) -> bool:
    return db.scalar(
        select(CompanyLeadCapability.id).where(
            CompanyLeadCapability.company_id == company_id,
            CompanyLeadCapability.capability_code == capability_code,
            CompanyLeadCapability.active.is_(True),
            CompanyLeadCapability.review_status == "APPROVED",
        )
    ) is not None


def require_lead_capability(db: Session, company_id: str | None, capability_code: str) -> None:
    require_active_company(db, company_id)
    if not has_lead_capability(db, company_id or "", capability_code):
        raise AppError(
            "COMPANY_CAPABILITY_REQUIRED",
            "当前公司尚未获得对应客资能力",
            403,
            {"capability_code": capability_code},
        )


def list_capabilities(db: Session, company_id: str) -> list[CompanyLeadCapability]:
    return list(
        db.scalars(
            select(CompanyLeadCapability)
            .where(CompanyLeadCapability.company_id == company_id)
            .order_by(CompanyLeadCapability.capability_code)
        ).all()
    )


def request_capability(db: Session, company_id: str, capability_code: str) -> CompanyLeadCapability:
    require_active_company(db, company_id)
    code = capability_code.strip().upper()
    if code not in VALID_CAPABILITIES:
        raise AppError("CAPABILITY_INVALID", "公司客资能力编码无效", 422)
    item = db.scalar(
        select(CompanyLeadCapability).where(
            CompanyLeadCapability.company_id == company_id,
            CompanyLeadCapability.capability_code == code,
        )
    )
    if item is None:
        item = CompanyLeadCapability(
            company_id=company_id,
            capability_code=code,
            active=False,
            review_status="PENDING",
        )
        db.add(item)
    elif item.review_status != "APPROVED":
        item.review_status = "PENDING"
        item.active = False
        item.reviewed_by = None
        item.reviewed_at = None
    db.flush()
    return item


def review_capability(
    db: Session,
    *,
    company_id: str,
    capability_code: str,
    approve: bool,
    reviewed_by: str,
) -> CompanyLeadCapability:
    item = db.scalar(
        select(CompanyLeadCapability).where(
            CompanyLeadCapability.company_id == company_id,
            CompanyLeadCapability.capability_code == capability_code.strip().upper(),
        )
    )
    if item is None:
        raise AppError("CAPABILITY_REQUEST_NOT_FOUND", "公司客资能力申请不存在", 404)
    item.review_status = "APPROVED" if approve else "REJECTED"
    item.active = approve
    item.reviewed_by = reviewed_by
    item.reviewed_at = datetime.now(timezone.utc)
    db.flush()
    return item


def list_service_areas(db: Session, company_id: str) -> list[CompanyServiceAreaV12]:
    return list(
        db.scalars(
            select(CompanyServiceAreaV12)
            .where(CompanyServiceAreaV12.company_id == company_id)
            .order_by(CompanyServiceAreaV12.is_primary_city.desc(), CompanyServiceAreaV12.region_code)
        ).all()
    )


def replace_service_areas(
    db: Session,
    *,
    company_id: str,
    region_codes: list[str],
    primary_city_code: str | None,
) -> list[CompanyServiceAreaV12]:
    require_active_company(db, company_id)
    cleaned = list(dict.fromkeys(code.strip() for code in region_codes if code.strip()))
    if not cleaned:
        raise AppError("SERVICE_AREA_REQUIRED", "至少配置一个服务区域", 422)
    if primary_city_code and primary_city_code not in cleaned:
        raise AppError("PRIMARY_CITY_INVALID", "主要城市必须包含在服务区域中", 422)
    regions = {
        region.code: region
        for region in db.scalars(select(Region).where(Region.code.in_(cleaned), Region.active.is_(True))).all()
    }
    missing = sorted(set(cleaned) - set(regions))
    if missing:
        raise AppError("REGION_NOT_FOUND", "存在无效或停用的地区编码", 422, {"region_codes": missing})
    db.execute(delete(CompanyServiceAreaV12).where(CompanyServiceAreaV12.company_id == company_id))
    items: list[CompanyServiceAreaV12] = []
    for code in cleaned:
        region = regions[code]
        item = CompanyServiceAreaV12(
            company_id=company_id,
            region_code=code,
            region_level=region.level,
            is_primary_city=code == primary_city_code,
            active=False,
            review_status="PENDING",
        )
        db.add(item)
        items.append(item)
    db.flush()
    return items


def review_service_area(
    db: Session,
    *,
    area_id: str,
    approve: bool,
    reviewed_by: str,
    note: str | None = None,
) -> CompanyServiceAreaV12:
    item = db.get(CompanyServiceAreaV12, area_id)
    if item is None:
        raise AppError("SERVICE_AREA_NOT_FOUND", "服务区域申请不存在", 404)
    item.review_status = "APPROVED" if approve else "REJECTED"
    item.active = approve
    item.reviewed_by = reviewed_by
    item.reviewed_at = datetime.now(timezone.utc)
    item.review_note = note.strip() if note else None
    db.flush()
    return item

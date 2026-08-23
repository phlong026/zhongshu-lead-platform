from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..core.models import Company, CompanyCapability, CompanyServiceRegion, DictionaryItem, PointsAccount, Region
from ..core.models_v12 import CompanyLeadCapability, CompanyServiceAreaV12
from ..core.security import decrypt_text, encrypt_text, hash_phone, mask_phone
from ..core.v12_enums import CompanyLeadCapabilityCode
from ..schemas.company import CompanyCreateBody, CompanySimpleCreateBody, CompanyUpdateBody

DEFAULT_RECEIVER_CATEGORIES = ("OLD_RENOVATION", "SELF_BUILD", "INTERIOR")


def company_to_dict(company: Company, include_finance: bool = False) -> dict:
    data = {
        "id": company.id,
        "code": company.code,
        "name": company.name,
        "status": company.status,
        "owner_name": company.owner_name,
        "contact_phone_masked": mask_phone(decrypt_text(company.contact_phone_encrypted) if company.contact_phone_encrypted else None),
        "level_code": company.level_code,
        "primary_user_id": company.primary_user_id,
        "region_codes": [r.region_code for r in company.service_regions if r.active],
        "capabilities": [
            {"category_code": c.category_code, "brand_code": c.brand_code}
            for c in company.capabilities
            if c.active
        ],
        "notes": company.notes,
        "wechat_bound": bool(company.primary_user_id),
    }
    if include_finance:
        data["points_balance"] = company.points_account.balance if company.points_account else 0
    return data


def create_company(db: Session, body: CompanyCreateBody) -> Company:
    if db.scalar(select(Company).where(Company.code == body.code)):
        raise AppError("COMPANY_CODE_EXISTS", "公司编码已存在", 409)
    phone = body.contact_phone
    company = Company(
        code=body.code,
        name=body.name,
        owner_name=body.owner_name,
        contact_phone_encrypted=encrypt_text(phone) if phone else None,
        contact_phone_hash=hash_phone(phone) if phone else None,
        level_code=body.level_code,
        notes=body.notes,
    )
    db.add(company)
    db.flush()
    db.add(PointsAccount(company_id=company.id, balance=0, version=1))
    replace_company_scope(db, company, body.region_codes, body.capabilities)
    return company


def _next_company_code(db: Session) -> str:
    for _ in range(5):
        code = f"JM-{uuid4().hex[:10].upper()}"
        if not db.scalar(select(Company.id).where(Company.code == code)):
            return code
    raise AppError("COMPANY_CODE_GENERATION_FAILED", "加盟商编码生成失败，请重试", 409)


def _simple_region_codes(db: Session, body: CompanySimpleCreateBody) -> dict[str, Region]:
    requested = [body.primary_city_code, *body.district_codes]
    if body.serve_all_districts:
        district_codes = db.scalars(
            select(Region.code).where(
                Region.parent_code == body.primary_city_code,
                Region.level == "DISTRICT",
                Region.active.is_(True),
            )
        ).all()
        requested.extend(district_codes)
    cleaned = list(dict.fromkeys(code.strip() for code in requested if code.strip()))
    if not cleaned:
        raise AppError("SERVICE_AREA_REQUIRED", "至少选择一个服务地区", 422)
    regions = {
        region.code: region
        for region in db.scalars(
            select(Region).where(Region.code.in_(cleaned), Region.active.is_(True))
        ).all()
    }
    missing = sorted(set(cleaned) - set(regions))
    if missing:
        raise AppError("REGION_NOT_FOUND", "存在无效或停用的地区", 422, {"region_codes": missing})
    primary = regions.get(body.primary_city_code)
    if primary is None or primary.level != "CITY":
        raise AppError("PRIMARY_CITY_LEVEL_INVALID", "服务城市必须选择城市级地区", 422)
    invalid = [
        code
        for code, region in regions.items()
        if code != body.primary_city_code
        and (region.level != "DISTRICT" or region.parent_code != body.primary_city_code)
    ]
    if invalid:
        raise AppError(
            "SERVICE_AREA_HIERARCHY_INVALID",
            "服务区县必须隶属于所选服务城市",
            422,
            {"region_codes": sorted(invalid), "primary_city_code": body.primary_city_code},
        )
    return regions


def create_simple_company(db: Session, body: CompanySimpleCreateBody, *, reviewed_by: str | None = None) -> tuple[Company, dict[str, str]]:
    regions = _simple_region_codes(db, body)
    company = Company(
        code=_next_company_code(db),
        name=body.name,
        owner_name=body.owner_name,
        contact_phone_encrypted=encrypt_text(body.contact_phone) if body.contact_phone else None,
        contact_phone_hash=hash_phone(body.contact_phone) if body.contact_phone else None,
        level_code=body.level_code,
        notes=body.notes,
    )
    db.add(company)
    db.flush()
    db.add(PointsAccount(company_id=company.id, balance=0, version=1))

    region_codes = sorted(regions)
    replace_company_scope(
        db,
        company,
        region_codes,
        [{"category_code": code, "brand_code": None} for code in default_receiver_categories(db)],
    )

    now = datetime.now(timezone.utc)
    db.add(
        CompanyLeadCapability(
            company_id=company.id,
            capability_code=CompanyLeadCapabilityCode.LEAD_RECEIVER.value,
            active=True,
            review_status="APPROVED",
            reviewed_by=reviewed_by,
            reviewed_at=now,
            review_note="后台创建加盟商时自动开通接单资格",
        )
    )
    for code in region_codes:
        region = regions[code]
        db.add(
            CompanyServiceAreaV12(
                company_id=company.id,
                region_code=code,
                region_level=region.level,
                is_primary_city=code == body.primary_city_code,
                active=True,
                review_status="APPROVED",
                reviewed_by=reviewed_by,
                reviewed_at=now,
                review_note="后台创建加盟商时自动确认服务地区",
            )
        )
    db.flush()
    return company, {
        "points_account": "READY",
        "receiver_capability": "APPROVED",
        "service_areas": "APPROVED",
    }


def default_receiver_categories(db: Session) -> tuple[str, ...]:
    categories = tuple(dict.fromkeys(
        db.scalars(
            select(DictionaryItem.code)
            .where(DictionaryItem.domain == "lead_category", DictionaryItem.active.is_(True))
            .order_by(DictionaryItem.sort_order, DictionaryItem.code)
        ).all()
    ))
    return categories or DEFAULT_RECEIVER_CATEGORIES


def update_company(db: Session, company: Company, body: CompanyUpdateBody) -> Company:
    for field in ["name", "owner_name", "level_code", "status", "notes"]:
        value = getattr(body, field)
        if value is not None:
            setattr(company, field, value)
    if body.contact_phone is not None:
        company.contact_phone_encrypted = encrypt_text(body.contact_phone) if body.contact_phone else None
        company.contact_phone_hash = hash_phone(body.contact_phone) if body.contact_phone else None
    if body.region_codes is not None or body.capabilities is not None:
        replace_company_scope(
            db,
            company,
            body.region_codes if body.region_codes is not None else [x.region_code for x in company.service_regions],
            body.capabilities if body.capabilities is not None else [
                {"category_code": x.category_code, "brand_code": x.brand_code} for x in company.capabilities
            ],
        )
    if body.status == "DISABLED":
        for user in company.members:
            user.session_version += 1
    return company


def replace_company_scope(db: Session, company: Company, region_codes: list[str], capabilities: list[dict]) -> None:
    db.execute(delete(CompanyServiceRegion).where(CompanyServiceRegion.company_id == company.id))
    db.execute(delete(CompanyCapability).where(CompanyCapability.company_id == company.id))
    for region_code in sorted(set(region_codes)):
        db.add(CompanyServiceRegion(company_id=company.id, region_code=region_code, active=True))
    seen: set[tuple[str, str | None]] = set()
    for item in capabilities:
        category = str(item.get("category_code") or "").strip()
        brand = item.get("brand_code")
        if not category or (category, brand) in seen:
            continue
        seen.add((category, brand))
        db.add(CompanyCapability(company_id=company.id, category_code=category, brand_code=brand, active=True))

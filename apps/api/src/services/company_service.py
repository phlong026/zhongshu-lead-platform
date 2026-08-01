from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..core.models import Company, CompanyCapability, CompanyServiceRegion, PointsAccount
from ..core.security import decrypt_text, encrypt_text, hash_phone, mask_phone
from ..schemas.company import CompanyCreateBody, CompanyUpdateBody


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

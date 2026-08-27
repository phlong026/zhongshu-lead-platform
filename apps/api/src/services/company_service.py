from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..core.models import (
    Assignment,
    Company,
    CompanyAccountRequest,
    CompanyCapability,
    CompanyServiceRegion,
    DictionaryItem,
    FollowUp,
    InviteToken,
    Lead,
    Notification,
    NotificationOutbox,
    PointsAccount,
    PointsLedger,
    Region,
    ReturnRequest,
    User,
    WechatIdentity,
)
from ..core.models_v12 import CompanyLeadCapability, CompanyServiceAreaV12, SupplierLeadReward
from ..core.security import decrypt_text, encrypt_text, hash_phone, mask_phone
from ..core.time import utcnow
from ..core.v12_enums import CompanyLeadCapabilityCode
from ..schemas.company import CompanyCreateBody, CompanySimpleCreateBody, CompanyUpdateBody
from .china_regions import city_by_code, district_by_code

DEFAULT_RECEIVER_CATEGORIES = ("OLD_RENOVATION", "SELF_BUILD", "INTERIOR")


def company_to_dict(company: Company, include_finance: bool = False) -> dict:
    data = {
        "id": company.id,
        "code": company.code,
        "name": company.name,
        "status": company.status,
        "is_test": company.is_test,
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
        is_test=body.is_test,
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
    _materialize_selected_regions(db, body)
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


def _materialize_selected_regions(db: Session, body: CompanySimpleCreateBody) -> None:
    """把用户从全国组件选中的地区接入现有派发地区模型。"""

    city = city_by_code(body.primary_city_code)
    if city is None:
        return

    if db.get(Region, city["code"]) is None:
        db.add(
            Region(
                code=city["code"],
                name=city["name"],
                level="CITY",
                parent_code=None,
                aliases=[city["name"]],
                active=True,
            )
        )

    requested_district_codes = (
        [district["code"] for district in city["districts"]]
        if body.serve_all_districts
        else body.district_codes
    )
    for code in dict.fromkeys(requested_district_codes):
        district = district_by_code(city, code)
        if district is None or db.get(Region, code) is not None:
            continue
        db.add(
            Region(
                code=district["code"],
                name=district["name"],
                level="DISTRICT",
                parent_code=city["code"],
                aliases=[district["name"]],
                active=True,
            )
        )
    db.flush()


def create_simple_company(
    db: Session,
    body: CompanySimpleCreateBody,
    *,
    approved_by: str | None = None,
) -> tuple[Company, dict[str, str]]:
    regions = _simple_region_codes(db, body)
    company = Company(
        code=_next_company_code(db),
        name=body.name,
        owner_name=body.owner_name,
        contact_phone_encrypted=encrypt_text(body.contact_phone) if body.contact_phone else None,
        contact_phone_hash=hash_phone(body.contact_phone) if body.contact_phone else None,
        level_code=body.level_code,
        is_test=body.is_test,
        notes=body.notes,
    )
    db.add(company)
    db.flush()
    db.add(PointsAccount(company_id=company.id, balance=0, version=1))

    region_codes = sorted(regions)
    approved_at = datetime.now(timezone.utc)
    db.add(
        CompanyLeadCapability(
            company_id=company.id,
            capability_code=CompanyLeadCapabilityCode.LEAD_RECEIVER.value,
            active=True,
            review_status="APPROVED",
            reviewed_by=approved_by,
            reviewed_at=approved_at,
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
                reviewed_by=approved_by,
                reviewed_at=approved_at,
                review_note="后台创建加盟商时自动开通服务地区",
            )
        )
    db.flush()
    return company, {
        "points_account": "READY",
        "receiver_capability": "READY",
        "service_areas": "READY",
    }


def default_receiver_categories(db: Session) -> tuple[str, ...]:
    categories = tuple(
        dict.fromkeys(
            db.scalars(
                select(DictionaryItem.code)
                .where(
                    DictionaryItem.domain == "lead_category",
                    DictionaryItem.active.is_(True),
                )
                .order_by(DictionaryItem.sort_order, DictionaryItem.code)
            ).all()
        )
    )
    return categories or DEFAULT_RECEIVER_CATEGORIES


def update_company(db: Session, company: Company, body: CompanyUpdateBody) -> Company:
    previous_status = company.status
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
    if body.status == "DISABLED" and previous_status != "DISABLED":
        for user in company.members:
            user.session_version += 1
        _cancel_company_invite_outboxes(db, company.id, reason="加盟商已停用")
        db.execute(
            update(InviteToken)
            .where(
                InviteToken.company_id == company.id,
                InviteToken.revoked_at.is_(None),
                InviteToken.used_at.is_(None),
                InviteToken.expires_at > utcnow(),
            )
            .values(revoked_at=utcnow())
            .execution_options(synchronize_session=False)
        )
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


def unbind_company_owner_wechat(
    db: Session,
    company_id: str,
    *,
    confirm_name: str,
) -> dict[str, object]:
    company = db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    if company is None:
        raise AppError("COMPANY_NOT_FOUND", "加盟商公司不存在", 404)
    if company.status != "DISABLED":
        raise AppError("COMPANY_MUST_BE_DISABLED", "请先停用加盟商，再解绑负责人微信", 409)
    if confirm_name != company.name:
        raise AppError("COMPANY_CONFIRMATION_MISMATCH", "输入的加盟商名称不匹配", 409)
    if not company.primary_user_id:
        raise AppError("COMPANY_OWNER_WECHAT_NOT_BOUND", "该加盟商尚未绑定负责人微信", 409)

    owner = db.get(User, company.primary_user_id)
    if owner is None or owner.company_id != company.id:
        raise AppError(
            "COMPANY_BINDING_INCONSISTENT",
            "负责人绑定数据不一致，请先进行数据核对",
            409,
        )

    identity = db.scalar(select(WechatIdentity).where(WechatIdentity.user_id == owner.id))
    if identity is None:
        raise AppError(
            "COMPANY_BINDING_INCONSISTENT",
            "负责人绑定数据不一致，请先进行数据核对",
            409,
        )

    previous_status = owner.status
    previous_session_version = owner.session_version
    company.primary_user_id = None
    owner.status = "DISABLED"
    owner.session_version += 1
    db.delete(identity)
    revoked_count = db.execute(
        update(InviteToken)
        .where(
            InviteToken.company_id == company.id,
            InviteToken.revoked_at.is_(None),
            InviteToken.used_at.is_(None),
        )
        .values(revoked_at=utcnow())
        .execution_options(synchronize_session=False)
    ).rowcount
    cancelled_delivery_count = _cancel_company_invite_outboxes(
        db,
        company.id,
        reason="负责人微信已解绑",
    )
    db.flush()
    return {
        "company_id": company.id,
        "unbound_user_id": owner.id,
        "revoked_invite_count": int(revoked_count or 0),
        "cancelled_invite_delivery_count": cancelled_delivery_count,
        "before": {
            "status": company.status,
            "primary_user_id": owner.id,
            "wechat_bound": True,
            "owner_user_status": previous_status,
            "owner_session_version": previous_session_version,
        },
        "after": {
            "status": company.status,
            "primary_user_id": None,
            "wechat_bound": False,
            "owner_user_status": owner.status,
            "owner_session_version": owner.session_version,
        },
    }


def company_business_blockers(db: Session, company_id: str) -> dict[str, int]:
    checks = {
        "account_requests": select(func.count(CompanyAccountRequest.id)).where(
            CompanyAccountRequest.company_id == company_id
        ),
        "leads": select(func.count(Lead.id)).where(Lead.supplier_company_id == company_id),
        "assignments": select(func.count(Assignment.id)).where(
            or_(
                Assignment.company_id == company_id,
                Assignment.supplier_company_id == company_id,
                Assignment.receiver_company_id == company_id,
            )
        ),
        "points_ledgers": select(func.count(PointsLedger.id)).where(
            PointsLedger.company_id == company_id
        ),
        "return_requests": select(func.count(ReturnRequest.id)).where(
            ReturnRequest.company_id == company_id
        ),
        "followups": select(func.count(FollowUp.id)).where(FollowUp.company_id == company_id),
        "supplier_rewards": select(func.count(SupplierLeadReward.id)).where(
            or_(
                SupplierLeadReward.supplier_company_id == company_id,
                SupplierLeadReward.receiver_company_id == company_id,
            )
        ),
    }
    blockers: dict[str, int] = {}
    for name, stmt in checks.items():
        count = int(db.scalar(stmt) or 0)
        if count > 0:
            blockers[name] = count
    account = db.scalar(select(PointsAccount).where(PointsAccount.company_id == company_id))
    if account and int(account.balance or 0) != 0:
        blockers["points_balance"] = int(account.balance or 0)
    return blockers


_BUSINESS_BLOCKER_LABELS = {
    "account_requests": "账号申请",
    "leads": "客资",
    "assignments": "派发记录",
    "points_ledgers": "积分流水",
    "return_requests": "退回记录",
    "followups": "跟进记录",
    "supplier_rewards": "供客奖励",
    "points_balance": "积分余额",
}


def _cancel_company_invite_outboxes(db: Session, company_id: str, *, reason: str) -> int:
    invite_ids = list(
        db.scalars(select(InviteToken.id).where(InviteToken.company_id == company_id)).all()
    )
    if not invite_ids:
        return 0
    result = db.execute(
        update(NotificationOutbox)
        .where(
            NotificationOutbox.aggregate_type == "invite",
            NotificationOutbox.aggregate_id.in_(invite_ids),
            NotificationOutbox.status.in_(["PENDING", "FAILED", "PROCESSING"]),
        )
        .values(status="CANCELLED", next_attempt_at=None, last_error=reason)
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


def mark_company_as_test(
    db: Session,
    company_id: str,
    *,
    confirm_name: str,
) -> dict[str, object]:
    company = db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    if company is None:
        raise AppError("COMPANY_NOT_FOUND", "加盟商公司不存在", 404)
    if company.status != "DISABLED":
        raise AppError("COMPANY_MUST_BE_DISABLED", "请先停用加盟商，再标记历史测试数据", 409)
    if company.is_test:
        raise AppError("COMPANY_ALREADY_TEST", "该加盟商已是测试主体", 409)
    if confirm_name != company.name:
        raise AppError("COMPANY_CONFIRMATION_MISMATCH", "输入的加盟商名称不匹配", 409)

    blockers = company_business_blockers(db, company.id)
    if blockers:
        raise AppError(
            "COMPANY_TEST_MARK_BLOCKED",
            "该加盟商存在业务数据，不能标记为可删除的测试数据",
            409,
            {
                "blocking_tables": sorted(blockers),
                "blockers": [_BUSINESS_BLOCKER_LABELS.get(name, name) for name in sorted(blockers)],
                "counts": blockers,
            },
        )

    company.is_test = True
    db.flush()
    return {
        "company_id": company.id,
        "before": {"status": company.status, "is_test": False},
        "after": {"status": company.status, "is_test": True},
    }


def delete_test_company(
    db: Session,
    company_id: str,
    *,
    confirm_name: str,
) -> dict[str, object]:
    company = db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    if company is None:
        raise AppError("COMPANY_NOT_FOUND", "加盟商公司不存在", 404)
    if company.status != "DISABLED":
        raise AppError("COMPANY_MUST_BE_DISABLED", "请先停用加盟商，再清理测试数据", 409)
    if not company.is_test:
        raise AppError("COMPANY_DELETE_TEST_ONLY", "正常加盟商只能停用，不允许删除", 409)
    if confirm_name != company.name:
        raise AppError("COMPANY_CONFIRMATION_MISMATCH", "输入的加盟商名称不匹配", 409)

    blockers = company_business_blockers(db, company.id)
    if blockers:
        raise AppError(
            "COMPANY_DELETE_BLOCKED",
            "该加盟商存在业务数据，只能停用，不允许删除",
            409,
            {
                "blocking_tables": sorted(blockers),
                "blockers": [_BUSINESS_BLOCKER_LABELS.get(name, name) for name in sorted(blockers)],
                "counts": blockers,
            },
        )

    members = list(db.scalars(select(User).where(User.company_id == company.id)).all())
    detached_user_ids: list[str] = []
    for user in members:
        db.execute(delete(WechatIdentity).where(WechatIdentity.user_id == user.id))
        user.status = "DISABLED"
        user.session_version += 1
        user.company_id = None
        detached_user_ids.append(user.id)

    _cancel_company_invite_outboxes(db, company.id, reason="邀请所属测试主体已删除")

    snapshot = {
        "id": company.id,
        "code": company.code,
        "name": company.name,
        "status": company.status,
        "is_test": company.is_test,
        "primary_user_id": company.primary_user_id,
        "member_count": len(members),
        "detached_user_ids": detached_user_ids,
    }
    company.primary_user_id = None
    db.execute(delete(Notification).where(Notification.company_id == company.id))
    db.execute(delete(InviteToken).where(InviteToken.company_id == company.id))
    db.execute(delete(CompanyLeadCapability).where(CompanyLeadCapability.company_id == company.id))
    db.execute(delete(CompanyServiceAreaV12).where(CompanyServiceAreaV12.company_id == company.id))
    db.execute(delete(CompanyServiceRegion).where(CompanyServiceRegion.company_id == company.id))
    db.execute(delete(CompanyCapability).where(CompanyCapability.company_id == company.id))
    db.execute(delete(PointsAccount).where(PointsAccount.company_id == company.id))
    db.delete(company)
    db.flush()
    return snapshot

from __future__ import annotations

import pytest

from apps.api.src.core.auth import Principal
from apps.api.src.core.errors import AppError
from apps.api.src.core.models import Company, Lead, Region, User
from apps.api.src.core.models_v12 import CompanyLeadCapability
from apps.api.src.core.security import fingerprint_phone
from apps.api.src.core.v12_enums import DuplicateDecision, LeadSourceKind, LeadV12Status
from apps.api.src.services.company_profile_v12 import (
    replace_service_areas,
    request_capability,
    review_capability,
    review_service_area,
)
from apps.api.src.services.dedup_v12 import classify_age, override_duplicate
from apps.api.src.services.lead_supply_v12 import (
    create_draft,
    discard_draft,
    reopen_rejected_supplier_lead,
    review_supplier_lead,
    submit_draft,
)


def _principal(user_id: str, company_id: str | None = None, *permissions: str) -> Principal:
    return Principal(
        user_id=user_id,
        display_name="测试用户",
        company_id=company_id,
        role_codes=frozenset(),
        permission_codes=frozenset(permissions),
        session_version=1,
    )


def _seed_identity(db, *, company_code: str = "C001") -> tuple[Company, User]:
    company = Company(code=company_code, name=f"测试公司-{company_code}", status="ACTIVE")
    db.add(company)
    db.flush()
    user = User(display_name="测试用户", status="ACTIVE", company_id=company.id)
    db.add(user)
    db.flush()
    return company, user


def _valid_values(phone: str = "13800138000") -> dict:
    return {
        "customer_name": "张先生",
        "phone": phone,
        "city": "武汉市",
        "region_code": "420100",
        "need_summary": "计划建设一套两层乡墅",
        "consent_confirmed": True,
    }


def _approve_supplier_capability(db, company: Company, user: User) -> None:
    request_capability(db, company.id, "LEAD_SUPPLIER")
    review_capability(
        db,
        company_id=company.id,
        capability_code="LEAD_SUPPLIER",
        approve=True,
        reviewed_by=user.id,
    )


def test_phone_fingerprint_normalizes_country_code() -> None:
    assert fingerprint_phone("+86 138-0013-8000", secret="test-secret") == fingerprint_phone(
        "13800138000", secret="test-secret"
    )
    assert fingerprint_phone("13800138000", secret="other-secret") != fingerprint_phone(
        "13800138000", secret="test-secret"
    )


def test_dedup_window_boundaries() -> None:
    assert classify_age(90)[0] is DuplicateDecision.HARD_DUPLICATE
    assert classify_age(91)[0] is DuplicateDecision.REWARD_DUPLICATE
    assert classify_age(180)[0] is DuplicateDecision.REWARD_DUPLICATE
    assert classify_age(181)[0] is DuplicateDecision.HISTORICAL_SUSPECT
    assert classify_age(366)[0] is DuplicateDecision.CLEAR


def test_platform_manual_submission_enters_ready_pool_without_pre_verification(db) -> None:
    db.add(Region(code="420100", name="武汉市", level="CITY", aliases=[], active=True))
    _, user = _seed_identity(db)
    principal = _principal(user.id, None, "lead.manual.manage")
    lead = create_draft(
        db,
        principal=principal,
        source_kind=LeadSourceKind.PLATFORM_MANUAL,
        values=_valid_values(),
    )
    result = submit_draft(db, lead=lead, principal=principal)
    db.commit()

    assert result.decision is DuplicateDecision.CLEAR
    assert lead.status == LeadV12Status.READY_DISPATCH.value
    assert lead.review_status == "APPROVED"
    assert lead.phone_fingerprint


def test_clear_dedup_result_cannot_be_artificially_overridden(db) -> None:
    db.add(Region(code="420100", name="武汉市", level="CITY", aliases=[], active=True))
    _, user = _seed_identity(db, company_code="CLEAR001")
    principal = _principal(user.id, None, "lead.manual.manage")
    lead = create_draft(
        db,
        principal=principal,
        source_kind=LeadSourceKind.PLATFORM_MANUAL,
        values=_valid_values("13900139000"),
    )
    result = submit_draft(db, lead=lead, principal=principal)
    assert result.decision is DuplicateDecision.CLEAR
    with pytest.raises(ValueError, match="仅重复或历史疑似结论"):
        override_duplicate(
            db,
            lead=lead,
            event_id=result.event_id,
            reason="错误尝试覆盖正常客资",
            approved_by=user.id,
        )


def test_recent_duplicate_is_blocked_and_can_be_audited_override(db) -> None:
    db.add(Region(code="420100", name="武汉市", level="CITY", aliases=[], active=True))
    _, user = _seed_identity(db)
    principal = _principal(user.id, None, "lead.manual.manage")
    first = create_draft(db, principal=principal, source_kind=LeadSourceKind.PLATFORM_MANUAL, values=_valid_values())
    submit_draft(db, lead=first, principal=principal)
    db.commit()

    second = create_draft(db, principal=principal, source_kind=LeadSourceKind.PLATFORM_MANUAL, values=_valid_values())
    result = submit_draft(db, lead=second, principal=principal)
    assert result.decision is DuplicateDecision.HARD_DUPLICATE
    assert second.status == LeadV12Status.DUPLICATE.value

    item = override_duplicate(
        db,
        lead=second,
        event_id=result.event_id,
        reason="业务复核确认系不同家庭成员的独立需求",
        approved_by=user.id,
    )
    db.commit()
    assert item.dedup_event_id == result.event_id
    assert second.status == LeadV12Status.READY_DISPATCH.value
    assert second.duplicate_status == DuplicateDecision.OVERRIDDEN.value


def test_supplier_upload_requires_approved_capability_and_review(db) -> None:
    db.add(Region(code="420100", name="武汉市", level="CITY", aliases=[], active=True))
    company, user = _seed_identity(db, company_code="SUP001")
    principal = _principal(user.id, company.id, "supplier.lead.manage")

    with pytest.raises(AppError) as exc_info:
        create_draft(db, principal=principal, source_kind=LeadSourceKind.SUPPLIER_H5, values=_valid_values())
    assert exc_info.value.code == "COMPANY_CAPABILITY_REQUIRED"

    request_capability(db, company.id, "LEAD_SUPPLIER")
    review_capability(
        db,
        company_id=company.id,
        capability_code="LEAD_SUPPLIER",
        approve=True,
        reviewed_by=user.id,
    )
    lead = create_draft(db, principal=principal, source_kind=LeadSourceKind.SUPPLIER_H5, values=_valid_values())
    result = submit_draft(db, lead=lead, principal=principal)
    assert result.decision is DuplicateDecision.CLEAR
    assert lead.status == LeadV12Status.PENDING_REVIEW.value

    review_result = review_supplier_lead(
        db,
        lead=lead,
        reviewer=principal,
        approve=True,
        note="资料与授权完整",
    )
    db.commit()
    assert review_result is not None
    assert lead.review_status == "APPROVED"
    assert lead.status == LeadV12Status.READY_DISPATCH.value


def test_supplier_can_discard_own_draft(db) -> None:
    company, user = _seed_identity(db, company_code="SUP-DISCARD")
    _approve_supplier_capability(db, company, user)
    principal = _principal(user.id, company.id, "supplier.lead.manage")
    lead = create_draft(
        db,
        principal=principal,
        source_kind=LeadSourceKind.SUPPLIER_H5,
        values={"customer_name": "待确认客户"},
    )
    lead_id = lead.id

    discard_draft(db, lead=lead, principal=principal)
    db.flush()

    assert db.get(Lead, lead_id) is None


def test_supplier_cannot_discard_another_company_draft(db) -> None:
    owner_company, owner_user = _seed_identity(db, company_code="SUP-OWNER")
    other_company, other_user = _seed_identity(db, company_code="SUP-OTHER")
    _approve_supplier_capability(db, owner_company, owner_user)
    _approve_supplier_capability(db, other_company, other_user)
    owner = _principal(owner_user.id, owner_company.id, "supplier.lead.manage")
    other = _principal(other_user.id, other_company.id, "supplier.lead.manage")
    lead = create_draft(
        db,
        principal=owner,
        source_kind=LeadSourceKind.SUPPLIER_H5,
        values={"customer_name": "归属公司一"},
    )

    with pytest.raises(AppError) as exc_info:
        discard_draft(db, lead=lead, principal=other)

    assert exc_info.value.code == "FORBIDDEN"


def test_supplier_cannot_discard_submitted_lead(db) -> None:
    db.add(Region(code="420100", name="武汉市", level="CITY", aliases=[], active=True))
    company, user = _seed_identity(db, company_code="SUP-SUBMITTED")
    _approve_supplier_capability(db, company, user)
    principal = _principal(user.id, company.id, "supplier.lead.manage")
    lead = create_draft(
        db,
        principal=principal,
        source_kind=LeadSourceKind.SUPPLIER_H5,
        values=_valid_values("13700137000"),
    )
    submit_draft(db, lead=lead, principal=principal)

    with pytest.raises(AppError) as exc_info:
        discard_draft(db, lead=lead, principal=principal)

    assert exc_info.value.code == "LEAD_NOT_EDITABLE"


def test_supplier_discard_rejects_platform_manual_draft(db) -> None:
    company, user = _seed_identity(db, company_code="SUP-SOURCE")
    principal = _principal(
        user.id,
        company.id,
        "lead.manual.manage",
        "supplier.lead.manage",
    )
    lead = create_draft(
        db,
        principal=principal,
        source_kind=LeadSourceKind.PLATFORM_MANUAL,
        values={"customer_name": "平台录入草稿"},
    )

    with pytest.raises(AppError) as exc_info:
        discard_draft(db, lead=lead, principal=principal)

    assert exc_info.value.code == "FORBIDDEN"


def test_rejected_supplier_lead_can_be_revised_and_resubmitted(db) -> None:
    db.add(Region(code="420100", name="武汉市", level="CITY", aliases=[], active=True))
    company, user = _seed_identity(db, company_code="SUP-REVISE")
    _approve_supplier_capability(db, company, user)
    principal = _principal(user.id, company.id, "supplier.lead.manage")
    lead = create_draft(
        db,
        principal=principal,
        source_kind=LeadSourceKind.SUPPLIER_H5,
        values=_valid_values("13600136000"),
    )
    submit_draft(db, lead=lead, principal=principal)
    review_supplier_lead(
        db,
        lead=lead,
        reviewer=principal,
        approve=False,
        note="请补充更具体的建房需求",
    )
    assert lead.status == LeadV12Status.INVALID.value

    reopen_rejected_supplier_lead(db, lead=lead, principal=principal)

    assert lead.status == LeadV12Status.DRAFT.value
    assert lead.review_status == "DRAFT"
    assert lead.review_note == "请补充更具体的建房需求"
    assert lead.submitted_at is None
    assert lead.reviewed_at is None

    lead.need_summary = "计划在武汉建设两层自住房，近期确认设计方案"
    submit_draft(db, lead=lead, principal=principal)

    assert lead.status == LeadV12Status.PENDING_REVIEW.value
    assert lead.review_status == "PENDING"
    assert lead.review_note is None


def test_supplier_cannot_revise_lead_before_platform_rejection(db) -> None:
    db.add(Region(code="420100", name="武汉市", level="CITY", aliases=[], active=True))
    company, user = _seed_identity(db, company_code="SUP-NOT-REJECTED")
    _approve_supplier_capability(db, company, user)
    principal = _principal(user.id, company.id, "supplier.lead.manage")
    lead = create_draft(
        db,
        principal=principal,
        source_kind=LeadSourceKind.SUPPLIER_H5,
        values=_valid_values("13500135000"),
    )
    submit_draft(db, lead=lead, principal=principal)

    with pytest.raises(AppError) as exc_info:
        reopen_rejected_supplier_lead(db, lead=lead, principal=principal)

    assert exc_info.value.code == "LEAD_REVISION_NOT_ALLOWED"


def test_supplier_company_cannot_use_pending_capability(db) -> None:
    company, user = _seed_identity(db, company_code="SUP002")
    request_capability(db, company.id, "LEAD_SUPPLIER")
    db.flush()
    item = db.query(CompanyLeadCapability).filter_by(company_id=company.id).one()
    assert item.review_status == "PENDING" and item.active is False
    principal = _principal(user.id, company.id, "supplier.lead.manage")
    with pytest.raises(AppError) as exc_info:
        create_draft(db, principal=principal, source_kind=LeadSourceKind.SUPPLIER_H5, values={})
    assert exc_info.value.code == "COMPANY_CAPABILITY_REQUIRED"


def test_company_service_areas_require_review_before_activation(db) -> None:
    db.add_all(
        [
            Region(code="420100", name="武汉市", level="CITY", aliases=[], active=True),
            Region(code="420106", name="武昌区", level="DISTRICT", parent_code="420100", aliases=[], active=True),
        ]
    )
    company, user = _seed_identity(db, company_code="AREA001")
    items = replace_service_areas(
        db,
        company_id=company.id,
        region_codes=["420100", "420106"],
        primary_city_code="420100",
    )
    assert all(item.review_status == "PENDING" and item.active is False for item in items)
    district = next(item for item in items if item.region_code == "420106")
    review_service_area(db, area_id=district.id, approve=True, reviewed_by=user.id, note="服务能力已核验")
    db.commit()
    assert district.review_status == "APPROVED"
    assert district.active is True


def test_service_area_removal_stays_active_until_platform_approval(db) -> None:
    db.add_all(
        [
            Region(code="420100", name="武汉市", level="CITY", aliases=[], active=True),
            Region(code="420106", name="武昌区", level="DISTRICT", parent_code="420100", aliases=[], active=True),
        ]
    )
    company, user = _seed_identity(db, company_code="AREA002")
    initial = replace_service_areas(
        db,
        company_id=company.id,
        region_codes=["420100", "420106"],
        primary_city_code="420100",
    )
    for item in initial:
        review_service_area(db, area_id=item.id, approve=True, reviewed_by=user.id)
    db.commit()

    changed = replace_service_areas(
        db,
        company_id=company.id,
        region_codes=["420100"],
        primary_city_code="420100",
    )
    district = next(item for item in changed if item.region_code == "420106")
    assert district.review_status == "PENDING"
    assert district.active is True
    assert district.review_note.startswith("[REMOVE_REQUEST]")

    review_service_area(db, area_id=district.id, approve=True, reviewed_by=user.id, note="确认停止服务")
    db.commit()
    assert district.review_status == "APPROVED"
    assert district.active is False

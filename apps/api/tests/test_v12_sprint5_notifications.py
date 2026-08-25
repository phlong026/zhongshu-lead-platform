from __future__ import annotations

from sqlalchemy import func, select

from apps.api.src.core import models_v12 as _models_v12  # noqa: F401
from apps.api.src.core.auth import Principal
from apps.api.src.core.models import AuditLog, Company, Lead, Notification, NotificationOutbox
from apps.api.src.core.models_v12 import CompanyLeadCapability, CompanyServiceAreaV12
from apps.api.src.services.audit import sanitize_audit_value, write_audit
from apps.api.src.services.auth_service import create_internal_user
from apps.api.src.services.notification_v12 import emit_business_notification


def principal(company_id: str) -> Principal:
    return Principal(
        user_id="ops-user",
        display_name="运营测试",
        company_id=company_id,
        role_codes=frozenset({"OPERATION"}),
        permission_codes=frozenset({"lead.supplier.review"}),
        session_version=1,
    )


def test_emit_business_notification_is_idempotent_and_traceable(db):
    company = Company(code="S5-NOTIFY", name="Sprint 5 通知测试公司")
    db.add(company)
    db.flush()

    first = emit_business_notification(
        db,
        event_key="v12:test:lead-1:submitted",
        event_type="V12_SUPPLIER_LEAD_SUBMITTED",
        company_id=company.id,
        title="客资已提交初审",
        body="平台已收到客资资料。",
        target="lead",
        business_id="lead-1",
        business_ids={"lead_id": "lead-1"},
    )
    second = emit_business_notification(
        db,
        event_key="v12:test:lead-1:submitted",
        event_type="V12_SUPPLIER_LEAD_SUBMITTED",
        company_id=company.id,
        title="重复调用不会重复创建",
        body="重复调用",
        target="lead",
        business_id="lead-1",
        business_ids={"lead_id": "lead-1"},
    )
    db.flush()

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert db.scalar(select(func.count(Notification.id))) == 1
    assert db.scalar(select(func.count(NotificationOutbox.id))) == 1

    notification = db.scalar(select(Notification))
    assert notification is not None
    assert notification.deep_link == "/h5/v12-workbench.html?view=lead&id=lead-1"
    assert first.payload["notification_id"] == notification.id
    assert first.payload["business_ids"] == {"lead_id": "lead-1"}


def test_v12_audit_projects_supplier_submit_notification(db):
    company = Company(code="S5-AUDIT", name="Sprint 5 审计投影公司")
    db.add(company)
    db.flush()
    lead = Lead(
        customer_name="张先生",
        phone_encrypted="ciphertext",
        phone_hash="legacy-hash",
        source_kind="SUPPLIER_H5",
        supplier_company_id=company.id,
        review_status="PENDING",
        status="PENDING_REVIEW",
    )
    db.add(lead)
    db.flush()

    write_audit(
        db,
        principal=principal(company.id),
        action="V12_SUPPLIER_LEAD_SUBMIT",
        resource_type="lead",
        resource_id=lead.id,
        company_id=company.id,
        after={"status": lead.status, "phone": "13800138000"},
        request_id="request-s5-notify",
    )
    db.flush()

    audit = db.scalar(select(AuditLog).where(AuditLog.resource_id == lead.id))
    notification = db.scalar(select(Notification).where(Notification.company_id == company.id))
    outbox = db.scalar(select(NotificationOutbox).where(NotificationOutbox.aggregate_id == lead.id))
    assert audit is not None
    assert audit.after_json["phone"] == "[REDACTED]"
    assert notification is not None
    assert notification.scene == "V12_SUPPLIER_LEAD_SUBMITTED"
    assert outbox is not None
    assert outbox.payload["business_ids"]["lead_id"] == lead.id


def test_company_profile_review_audit_notifies_the_company_owner(db):
    company = Company(code="S6-PROFILE", name="阶段六资料审核通知公司")
    db.add(company)
    db.flush()
    owner = create_internal_user(
        db,
        username="stage6-profile-owner",
        password="simple88",
        display_name="阶段六负责人",
        role_code="FRANCHISE_OWNER",
        company_id=company.id,
    )
    company.primary_user_id = owner.id
    capability = CompanyLeadCapability(
        company_id=company.id,
        capability_code="LEAD_RECEIVER",
        active=True,
        review_status="APPROVED",
    )
    db.add(capability)
    db.flush()

    write_audit(
        db,
        principal=principal(company.id),
        action="V12_COMPANY_CAPABILITY_REVIEW",
        resource_type="company_lead_capability",
        resource_id=capability.id,
        company_id=company.id,
        after={"capability_code": "LEAD_RECEIVER", "active": True, "review_status": "APPROVED"},
        request_id="request-s6-profile-review",
    )
    db.flush()

    notification = db.scalar(
        select(Notification).where(Notification.company_id == company.id)
    )
    outbox = db.scalar(
        select(NotificationOutbox).where(NotificationOutbox.aggregate_id == company.id)
    )
    assert notification is not None
    assert notification.scene == "V12_COMPANY_PROFILE_APPROVED"
    assert notification.deep_link == f"/h5/v12-workbench.html?view=profile&id={company.id}"
    assert outbox is not None
    assert outbox.event_type == "V12_COMPANY_PROFILE_APPROVED"
    assert len(outbox.event_key) <= 128
    assert outbox.payload["company_id"] == company.id
    assert company.primary_user_id == owner.id


def test_approved_service_area_removal_is_not_reported_as_a_rejection(db):
    company = Company(code="S6-REMOVE", name="阶段六服务区域移除通知公司")
    db.add(company)
    db.flush()
    area = CompanyServiceAreaV12(
        company_id=company.id,
        region_code="310000",
        region_level="CITY",
        is_primary_city=True,
        active=False,
        review_status="APPROVED",
        review_note="[REMOVE_REQUEST] 加盟商申请停止该服务区域",
    )
    db.add(area)
    db.flush()

    write_audit(
        db,
        principal=principal(company.id),
        action="V12_COMPANY_SERVICE_AREA_REVIEW",
        resource_type="company_service_area_v12",
        resource_id=area.id,
        company_id=company.id,
        after={
            "region_code": area.region_code,
            "active": False,
            "review_status": "APPROVED",
            "review_note": "移除申请已批准",
            "request_type": "REMOVE",
        },
        request_id="request-s6-service-area-removal",
    )
    db.flush()

    notification = db.scalar(
        select(Notification).where(Notification.company_id == company.id)
    )
    assert notification is not None
    assert notification.scene == "V12_COMPANY_PROFILE_APPROVED"
    assert notification.title == "服务区域移除已通过"


def test_audit_sanitizer_preserves_masked_phone_only():
    value = sanitize_audit_value(
        {
            "phone": "13800138000",
            "phone_masked": "138****8000",
            "nested": {"authorization": "Bearer secret", "mobile": "13900000000"},
        }
    )
    assert value == {
        "phone": "[REDACTED]",
        "phone_masked": "138****8000",
        "nested": {"authorization": "[REDACTED]", "mobile": "[REDACTED]"},
    }

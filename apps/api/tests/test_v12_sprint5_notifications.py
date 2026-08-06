from __future__ import annotations

from sqlalchemy import func, select

from apps.api.src.core import models_v12 as _models_v12  # noqa: F401
from apps.api.src.core.auth import Principal
from apps.api.src.core.models import AuditLog, Company, Lead, Notification, NotificationOutbox
from apps.api.src.services.audit import sanitize_audit_value, write_audit
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

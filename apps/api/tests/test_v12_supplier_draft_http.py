from __future__ import annotations

from sqlalchemy import select

from apps.api.src.core.models import AuditLog, Company, Lead, Notification, NotificationOutbox, User
from apps.api.src.core.models_v12 import CompanyLeadCapability
from apps.api.src.core.security import encrypt_text, hash_phone
from apps.api.src.core.v12_enums import LeadSourceKind, LeadV12Status, VerificationTaskType
from apps.api.src.services.auth_service import create_internal_user
from apps.api.src.services.verification_service import publish_template


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def _data(response):
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["code"] == "OK"
    return payload["data"]


def _approve_supplier_capability(factory) -> tuple[str, str]:
    with factory() as db:
        company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        supplier = db.scalar(select(User).where(User.username == "franchise_demo"))
        assert company is not None and supplier is not None
        capability = db.scalar(
            select(CompanyLeadCapability).where(
                CompanyLeadCapability.company_id == company.id,
                CompanyLeadCapability.capability_code == "LEAD_SUPPLIER",
            )
        )
        if capability is None:
            capability = CompanyLeadCapability(
                company_id=company.id,
                capability_code="LEAD_SUPPLIER",
            )
            db.add(capability)
        capability.active = True
        capability.review_status = "APPROVED"
        db.commit()
        return company.id, supplier.id


def _valid_lead_body(phone: str) -> dict:
    return {
        "customer_name": "接口验收客户",
        "phone": phone,
        "city": "上海市",
        "region_code": "310000",
        "need_summary": "计划建设两层自住房，近期确认设计方案",
        "consent_confirmed": True,
    }


def _lead(
    *,
    source_kind: LeadSourceKind,
    submitter_user_id: str,
    supplier_company_id: str | None,
    status: LeadV12Status,
    review_status: str,
    phone: str,
) -> Lead:
    return Lead(
        source_type=source_kind.value,
        source_kind=source_kind.value,
        submitter_user_id=submitter_user_id,
        supplier_company_id=supplier_company_id,
        customer_name="边界验收客户",
        phone_encrypted=encrypt_text(phone),
        phone_hash=hash_phone(phone),
        consent_confirmed=status is not LeadV12Status.DRAFT,
        city="上海市",
        region_code="310000",
        need_summary="用于验证跨公司对象状态不可见",
        status=status.value,
        review_status=review_status,
        raw_payload={},
    )


def test_supplier_draft_delete_route_is_scoped_and_audited(api_client) -> None:
    client, factory = api_client
    _approve_supplier_capability(factory)
    supplier = _login(client, "franchise_demo", "Franchise123!")

    draft = _data(
        client.post(
            "/api/v1/v1.2/supplier/leads",
            headers=supplier,
            json={"customer_name": "待确认客户"},
        )
    )
    deleted = _data(
        client.delete(
            f"/api/v1/v1.2/supplier/leads/{draft['id']}",
            headers=supplier,
        )
    )
    assert deleted == {"id": draft["id"]}
    assert client.get(
        f"/api/v1/v1.2/supplier/leads/{draft['id']}",
        headers=supplier,
    ).status_code == 404

    submitted = _data(
        client.post(
            "/api/v1/v1.2/supplier/leads",
            headers=supplier,
            json=_valid_lead_body("13900139011"),
        )
    )
    _data(
        client.post(
            f"/api/v1/v1.2/supplier/leads/{submitted['id']}/submit",
            headers=supplier,
        )
    )
    blocked = client.delete(
        f"/api/v1/v1.2/supplier/leads/{submitted['id']}",
        headers=supplier,
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "LEAD_NOT_EDITABLE"

    with factory() as db:
        assert db.get(Lead, draft["id"]) is None
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "V12_SUPPLIER_LEAD_DRAFT_DELETE",
                AuditLog.resource_id == draft["id"],
            )
        )
        assert audit is not None


def test_supplier_employee_can_only_read_own_supplier_leads(api_client) -> None:
    client, factory = api_client
    company_id, _ = _approve_supplier_capability(factory)
    with factory() as db:
        employee = create_internal_user(
            db,
            username="supplier_employee_scope",
            password="Employee123!",
            display_name="供资员工范围测试",
            role_code="FRANCHISE_EMPLOYEE",
            company_id=company_id,
        )
        db.commit()
        employee_id = employee.id

    owner = _login(client, "franchise_demo", "Franchise123!")
    owner_lead = _data(
        client.post(
            "/api/v1/v1.2/supplier/leads",
            headers=owner,
            json={"customer_name": "负责人录入的草稿"},
        )
    )
    employee = _login(client, "supplier_employee_scope", "Employee123!")
    employee_lead = _data(
        client.post(
            "/api/v1/v1.2/supplier/leads",
            headers=employee,
            json={"customer_name": "员工本人录入的草稿"},
        )
    )

    listed = _data(client.get("/api/v1/v1.2/supplier/leads", headers=employee))
    assert listed["total"] == 1
    assert [item["id"] for item in listed["items"]] == [employee_lead["id"]]
    denied = client.get(
        f"/api/v1/v1.2/supplier/leads/{owner_lead['id']}",
        headers=employee,
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "SUPPLIER_LEAD_NOT_OWNED"

    own = _data(
        client.get(
            f"/api/v1/v1.2/supplier/leads/{employee_lead['id']}",
            headers=employee,
        )
    )
    assert own["submitter_user_id"] == employee_id


def test_cross_company_delete_and_revise_do_not_expose_lead_state(api_client) -> None:
    client, factory = api_client
    own_company_id, supplier_user_id = _approve_supplier_capability(factory)
    supplier = _login(client, "franchise_demo", "Franchise123!")

    with factory() as db:
        foreign_company = Company(
            code="FOREIGN-SUPPLIER",
            name="外部供应商",
            status="ACTIVE",
        )
        db.add(foreign_company)
        db.flush()
        operation = db.scalar(select(User).where(User.username == "operation"))
        assert operation is not None
        leads = [
            _lead(
                source_kind=LeadSourceKind.SUPPLIER_H5,
                submitter_user_id=operation.id,
                supplier_company_id=foreign_company.id,
                status=LeadV12Status.DRAFT,
                review_status="DRAFT",
                phone="13900139021",
            ),
            _lead(
                source_kind=LeadSourceKind.SUPPLIER_H5,
                submitter_user_id=operation.id,
                supplier_company_id=foreign_company.id,
                status=LeadV12Status.PENDING_REVIEW,
                review_status="PENDING",
                phone="13900139022",
            ),
            _lead(
                source_kind=LeadSourceKind.SUPPLIER_H5,
                submitter_user_id=operation.id,
                supplier_company_id=foreign_company.id,
                status=LeadV12Status.INVALID,
                review_status="REJECTED",
                phone="13900139023",
            ),
            _lead(
                source_kind=LeadSourceKind.PLATFORM_MANUAL,
                submitter_user_id=supplier_user_id,
                supplier_company_id=None,
                status=LeadV12Status.DRAFT,
                review_status="DRAFT",
                phone="13900139024",
            ),
        ]
        db.add_all(leads)
        db.commit()
        lead_ids = [lead.id for lead in leads]

    for lead_id in lead_ids:
        response = client.delete(
            f"/api/v1/v1.2/supplier/leads/{lead_id}",
            headers=supplier,
        )
        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"

    for lead_id in lead_ids:
        response = client.post(
            f"/api/v1/v1.2/supplier/leads/{lead_id}/revise",
            headers=supplier,
        )
        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"

    assert own_company_id


def test_rejected_supplier_lead_can_revise_and_resubmit_over_http(api_client) -> None:
    client, factory = api_client
    company_id, _ = _approve_supplier_capability(factory)
    supplier = _login(client, "franchise_demo", "Franchise123!")
    admin = _login(client, "admin", "Admin123!")

    lead = _data(
        client.post(
            "/api/v1/v1.2/supplier/leads",
            headers=supplier,
            json=_valid_lead_body("+86 139-0013-9031"),
        )
    )
    submitted = _data(
        client.post(
            f"/api/v1/v1.2/supplier/leads/{lead['id']}/submit",
            headers=supplier,
        )
    )
    assert submitted["lead"]["status"] == "PENDING_REVIEW"

    rejected = _data(
        client.post(
            f"/api/v1/v1.2/admin/supplier-leads/{lead['id']}/review",
            headers=admin,
            json={"decision": "REJECT", "note": "请补充更具体的施工计划"},
        )
    )
    assert rejected["lead"]["status"] == "INVALID"

    revised = _data(
        client.post(
            f"/api/v1/v1.2/supplier/leads/{lead['id']}/revise",
            headers=supplier,
        )
    )
    assert revised["status"] == "DRAFT"
    assert revised["review_note"] == "请补充更具体的施工计划"

    _data(
        client.patch(
            f"/api/v1/v1.2/supplier/leads/{lead['id']}",
            headers=supplier,
            json={"need_summary": "已补充施工时间、地点和预算安排"},
        )
    )
    resubmitted = _data(
        client.post(
            f"/api/v1/v1.2/supplier/leads/{lead['id']}/submit",
            headers=supplier,
        )
    )
    assert resubmitted["lead"]["status"] == "PENDING_REVIEW"
    assert resubmitted["lead"]["review_status"] == "PENDING"
    assert resubmitted["lead"]["review_note"] is None

    blocked = client.post(
        f"/api/v1/v1.2/supplier/leads/{lead['id']}/revise",
        headers=supplier,
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "LEAD_REVISION_NOT_ALLOWED"

    rejected_again = _data(
        client.post(
            f"/api/v1/v1.2/admin/supplier-leads/{lead['id']}/review",
            headers=admin,
            json={"decision": "INVALID", "note": "补正后仍缺少可核验的客户意向说明"},
        )
    )
    assert rejected_again["lead"]["status"] == "INVALID"

    with factory() as db:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "V12_SUPPLIER_LEAD_REVISE",
                AuditLog.resource_id == lead["id"],
                AuditLog.company_id == company_id,
            )
        )
        assert audit is not None
        submissions = db.scalars(
            select(AuditLog)
            .where(
                AuditLog.action == "V12_SUPPLIER_LEAD_SUBMIT",
                AuditLog.resource_id == lead["id"],
            )
            .order_by(AuditLog.created_at.asc())
        ).all()
        assert len(submissions) == 2
        assert submissions[0].after_json["submission_snapshot"]["need_summary"] == _valid_lead_body("0")["need_summary"]
        assert submissions[1].after_json["submission_snapshot"]["need_summary"] == "已补充施工时间、地点和预算安排"
        submitted_notifications = db.scalars(
            select(Notification).where(
                Notification.company_id == company_id,
                Notification.scene == "V12_SUPPLIER_LEAD_SUBMITTED",
            )
        ).all()
        rejected_notifications = db.scalars(
            select(Notification).where(
                Notification.company_id == company_id,
                Notification.scene == "V12_SUPPLIER_LEAD_REJECTED",
            )
        ).all()
        submission_outboxes = db.scalars(
            select(NotificationOutbox).where(
                NotificationOutbox.aggregate_id == lead["id"],
                NotificationOutbox.event_type == "V12_SUPPLIER_LEAD_SUBMITTED",
            )
        ).all()
        assert len(submitted_notifications) == 2
        assert len(rejected_notifications) == 2
        assert len(submission_outboxes) == 2
        assert len({item.event_key for item in submission_outboxes}) == 2


def test_supplier_initial_review_can_require_assigned_telesales_verification(api_client) -> None:
    client, factory = api_client
    _approve_supplier_capability(factory)
    with factory() as db:
        telesales = db.scalar(select(User).where(User.username == "telesales"))
        assert telesales is not None
        publish_template(
            db,
            code="PRE_DISPATCH",
            name="前置事实核验",
            schema={"fields": []},
        )
        db.commit()
        telesales_id = telesales.id

    supplier = _login(client, "franchise_demo", "Franchise123!")
    operation = _login(client, "operation", "Operation123!")
    initial_body = _valid_lead_body("13900139032")
    lead = _data(
        client.post(
            "/api/v1/v1.2/supplier/leads",
            headers=supplier,
            json=initial_body,
        )
    )
    _data(
        client.post(
            f"/api/v1/v1.2/supplier/leads/{lead['id']}/submit",
            headers=supplier,
        )
    )

    reviewed = _data(
        client.post(
            f"/api/v1/v1.2/admin/supplier-leads/{lead['id']}/review",
            headers=operation,
            json={
                "decision": "INFO_INCOMPLETE",
                "note": "客户意向与预算还需要电话确认",
                "assignee_user_id": telesales_id,
                "pre_dispatch_reason": "补齐客户意向、预算和可联系时间",
            },
        )
    )
    assert reviewed["lead"]["status"] == LeadV12Status.PENDING_TELESALES_VERIFY.value
    assert reviewed["lead"]["review_status"] == "PENDING"
    assert reviewed["task"]["task_type"] == VerificationTaskType.PRE_DISPATCH_VERIFY.value
    assert reviewed["task"]["assignee_user_id"] == telesales_id
    assert reviewed["task"]["due_at"] is not None

    with factory() as db:
        review_audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "V12_SUPPLIER_LEAD_REVIEW",
                AuditLog.resource_id == lead["id"],
            )
        )
        assert review_audit is not None
        assert review_audit.after_json["review_decision"] == "INFO_INCOMPLETE"
        assert review_audit.after_json["submission_snapshot"]["need_summary"] == initial_body["need_summary"]
        task_audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "V12_PRE_DISPATCH_VERIFY_ASSIGN",
                AuditLog.resource_id == reviewed["task"]["id"],
            )
        )
        assert task_audit is not None
        notification = db.scalar(
            select(Notification).where(
                Notification.scene == "V12_SUPPLIER_LEAD_TELESALES_VERIFY_REQUIRED"
            )
        )
        assert notification is not None


def test_supplier_approval_notification_keys_fit_outbox_limit(api_client) -> None:
    client, factory = api_client
    _approve_supplier_capability(factory)
    supplier = _login(client, "franchise_demo", "Franchise123!")
    operation = _login(client, "operation", "Operation123!")
    lead = _data(
        client.post(
            "/api/v1/v1.2/supplier/leads",
            headers=supplier,
            json=_valid_lead_body("13900139033"),
        )
    )
    _data(
        client.post(
            f"/api/v1/v1.2/supplier/leads/{lead['id']}/submit",
            headers=supplier,
        )
    )
    reviewed = _data(
        client.post(
            f"/api/v1/v1.2/admin/supplier-leads/{lead['id']}/review",
            headers=operation,
            json={"decision": "QUALIFIED", "note": "资料完整，可进入待派发池"},
        )
    )
    assert reviewed["lead"]["status"] == LeadV12Status.READY_DISPATCH.value

    with factory() as db:
        outboxes = db.scalars(
            select(NotificationOutbox).where(NotificationOutbox.aggregate_id == lead["id"])
        ).all()
        assert any(item.event_type == "V12_LEAD_DISPATCH_REQUIRED" for item in outboxes)
        assert all(len(item.event_key) <= 128 for item in outboxes)


def test_platform_draft_can_enter_telesales_then_return_to_operation_rework(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        telesales = db.scalar(select(User).where(User.username == "telesales"))
        operation_user = db.scalar(select(User).where(User.username == "operation"))
        assert telesales is not None and operation_user is not None
        publish_template(
            db,
            code="PRE_DISPATCH",
            name="前置事实核验",
            schema={"fields": []},
        )
        db.commit()
        telesales_id = telesales.id
        operation_id = operation_user.id

    operation = _login(client, "operation", "Operation123!")
    telesales = _login(client, "telesales", "Telesales123!")
    platform_draft = _data(
        client.post(
            "/api/v1/v1.2/platform/leads",
            headers=operation,
            json={
                "customer_name": "待电话确认的平台客户",
                "phone": "13900139034",
                "city": "上海市",
            },
        )
    )
    assigned = _data(
        client.post(
            f"/api/v1/v1.2/admin/leads/{platform_draft['id']}/pre-dispatch-verification",
            headers=operation,
            json={
                "assignee_user_id": telesales_id,
                "reason": "缺少客户授权、联系方式和需求说明，需要电话补充",
            },
        )
    )
    assert assigned["lead"]["status"] == LeadV12Status.PENDING_TELESALES_VERIFY.value
    assert assigned["lead"]["source_kind"] == LeadSourceKind.PLATFORM_MANUAL.value
    assert assigned["task_type"] == VerificationTaskType.PRE_DISPATCH_VERIFY.value

    _data(
        client.post(
            f"/api/v1/v1.2/pre-dispatch-verifications/tasks/{assigned['id']}/start",
            headers=telesales,
        )
    )
    _data(
        client.post(
            f"/api/v1/v1.2/pre-dispatch-verifications/tasks/{assigned['id']}/submit",
            headers=telesales,
            json={
                "contact_result": "CONNECTED",
                "conclusion": "INFO_INCOMPLETE",
                "note": "客户愿意继续沟通，但尚未确认具体需求和授权方式",
            },
        )
    )
    disposition = _data(
        client.post(
            f"/api/v1/v1.2/admin/leads/{platform_draft['id']}/pre-dispatch-disposition",
            headers=operation,
            json={"decision": "RETURN_REWORK", "note": "平台补充客户授权和明确需求后再提交"},
        )
    )
    assert disposition["status"] == LeadV12Status.DRAFT.value

    reworked = _data(
        client.patch(
            f"/api/v1/v1.2/platform/leads/{platform_draft['id']}",
            headers=operation,
            json=_valid_lead_body("13900139034"),
        )
    )
    assert reworked["source_kind"] == LeadSourceKind.PLATFORM_MANUAL.value
    assert reworked["supplier_company_id"] is None
    assert reworked["status"] == LeadV12Status.DRAFT.value

    with factory() as db:
        operation_notifications = db.scalars(
            select(Notification).where(
                Notification.user_id == operation_id,
                Notification.scene.in_(
                    {
                        "V12_PRE_DISPATCH_OPERATION_REQUIRED",
                        "V12_PLATFORM_LEAD_DISPOSITION",
                    }
                ),
            )
        ).all()
        links_by_scene = {item.scene: item.deep_link for item in operation_notifications}
        assert links_by_scene["V12_PRE_DISPATCH_OPERATION_REQUIRED"] == (
            f"/admin/v12-operations.html?view=telesales&id={assigned['id']}"
        )
        assert links_by_scene["V12_PLATFORM_LEAD_DISPOSITION"] == (
            f"/admin/v12-operations.html?view=leads&id={platform_draft['id']}"
        )
        outboxes = db.scalars(
            select(NotificationOutbox).where(
                NotificationOutbox.aggregate_id.in_([platform_draft["id"], assigned["id"]])
            )
        ).all()
        assert {
            "V12_PRE_DISPATCH_OPERATION_REQUIRED",
            "V12_PLATFORM_LEAD_DISPOSITION",
        }.issubset({item.event_type for item in outboxes})
        assert all(len(item.event_key) <= 128 for item in outboxes)


def test_platform_draft_without_phone_cannot_enter_telesales_verification(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        telesales = db.scalar(select(User).where(User.username == "telesales"))
        assert telesales is not None
        telesales_id = telesales.id

    operation = _login(client, "operation", "Operation123!")
    draft = _data(
        client.post(
            "/api/v1/v1.2/platform/leads",
            headers=operation,
            json={"customer_name": "没有联系电话的平台客户", "city": "上海市"},
        )
    )

    blocked = client.post(
        f"/api/v1/v1.2/admin/leads/{draft['id']}/pre-dispatch-verification",
        headers=operation,
        json={"assignee_user_id": telesales_id, "reason": "需电话补充客户需求"},
    )

    assert blocked.status_code == 422
    assert blocked.json()["code"] == "PRE_DISPATCH_PHONE_REQUIRED"


def test_supplier_draft_cannot_bypass_initial_review_into_telesales_verification(api_client) -> None:
    client, factory = api_client
    _approve_supplier_capability(factory)
    with factory() as db:
        telesales = db.scalar(select(User).where(User.username == "telesales"))
        assert telesales is not None
        telesales_id = telesales.id

    supplier = _login(client, "franchise_demo", "Franchise123!")
    operation = _login(client, "operation", "Operation123!")
    draft = _data(
        client.post(
            "/api/v1/v1.2/supplier/leads",
            headers=supplier,
            json=_valid_lead_body("13900139035"),
        )
    )

    blocked = client.post(
        f"/api/v1/v1.2/admin/leads/{draft['id']}/pre-dispatch-verification",
        headers=operation,
        json={"assignee_user_id": telesales_id, "reason": "错误尝试绕过初审"},
    )

    assert blocked.status_code == 409
    assert blocked.json()["code"] == "PRE_DISPATCH_LEAD_STATE_INVALID"


def test_platform_endpoints_reject_supplier_lead_ids(api_client) -> None:
    client, factory = api_client
    _approve_supplier_capability(factory)
    supplier = _login(client, "franchise_demo", "Franchise123!")
    operation = _login(client, "operation", "Operation123!")
    draft = _data(
        client.post(
            "/api/v1/v1.2/supplier/leads",
            headers=supplier,
            json={"customer_name": "不能走平台接口的加盟商草稿"},
        )
    )

    update = client.patch(
        f"/api/v1/v1.2/platform/leads/{draft['id']}",
        headers=operation,
        json={"need_summary": "错误入口"},
    )
    submit = client.post(
        f"/api/v1/v1.2/platform/leads/{draft['id']}/submit",
        headers=operation,
    )

    assert update.status_code == 409
    assert update.json()["code"] == "LEAD_SOURCE_INVALID"
    assert submit.status_code == 409
    assert submit.json()["code"] == "LEAD_SOURCE_INVALID"

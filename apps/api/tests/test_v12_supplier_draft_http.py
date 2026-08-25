from __future__ import annotations

from sqlalchemy import select

from apps.api.src.core.models import AuditLog, Company, Lead, User
from apps.api.src.core.models_v12 import CompanyLeadCapability
from apps.api.src.core.security import encrypt_text, hash_phone
from apps.api.src.core.v12_enums import LeadSourceKind, LeadV12Status
from apps.api.src.services.auth_service import create_internal_user


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

    with factory() as db:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "V12_SUPPLIER_LEAD_REVISE",
                AuditLog.resource_id == lead["id"],
                AuditLog.company_id == company_id,
            )
        )
        assert audit is not None

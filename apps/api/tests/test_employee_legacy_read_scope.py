from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from apps.api.src.core.enums import AssignmentStatus
from apps.api.src.core.models import Assignment, Company, Lead, PointsAccount, User
from apps.api.src.core.security import encrypt_text, hash_phone
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


def _lead(*, name: str, phone: str) -> Lead:
    return Lead(
        source_type="PLATFORM_MANUAL",
        source_kind="PLATFORM_MANUAL",
        customer_name=name,
        phone_encrypted=encrypt_text(phone),
        phone_hash=hash_phone(phone),
        city="上海市",
        district="浦东新区",
        region_code="310115",
        need_summary="用于验证旧接口读权限隔离",
        status="CLAIMED",
        review_status="APPROVED",
        imported_at=datetime.now(timezone.utc),
    )


def _assignment(
    *,
    lead: Lead,
    company: Company,
    assigned_by: str,
    internal_assignee_user_id: str,
    status: str = AssignmentStatus.CLAIMED.value,
) -> Assignment:
    return Assignment(
        lead_id=lead.id,
        company_id=company.id,
        status=status,
        points_price=100,
        price_version=1,
        lead_snapshot={
            "customer_name": lead.customer_name,
            "city": lead.city,
            "district": lead.district,
            "need_summary": lead.need_summary,
        },
        assigned_by=assigned_by,
        internal_assignee_user_id=internal_assignee_user_id,
        internal_assigned_by=assigned_by,
        claimed_at=(
            datetime.now(timezone.utc)
            if status == AssignmentStatus.CLAIMED.value
            else None
        ),
    )


def test_employee_cannot_read_cross_company_legacy_details(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        attacker = db.scalar(
            select(User).where(User.username == "franchise_employee_demo")
        )
        operator = db.scalar(select(User).where(User.username == "operation"))
        assert attacker is not None and operator is not None

        target_company = Company(code="LEGACY-CROSS", name="旧接口跨公司目标")
        db.add(target_company)
        db.flush()
        target_owner = create_internal_user(
            db,
            username="legacy-cross-owner",
            password="Owner123!",
            display_name="跨公司负责人",
            role_code="FRANCHISE_OWNER",
            company_id=target_company.id,
        )
        target_company.primary_user_id = target_owner.id
        target_lead = _lead(name="跨公司客户", phone="13900139101")
        db.add(target_lead)
        db.flush()
        target_assignment = _assignment(
            lead=target_lead,
            company=target_company,
            assigned_by=operator.id,
            internal_assignee_user_id=target_owner.id,
        )
        db.add_all(
            [target_assignment, PointsAccount(company_id=target_company.id, balance=1000)]
        )
        db.commit()
        lead_id = target_lead.id
        assignment_id = target_assignment.id

    employee_headers = _login(client, "franchise_employee_demo", "Employee123!")
    responses = [
        client.get(f"/api/v1/leads/{lead_id}", headers=employee_headers),
        client.get(
            f"/api/v1/dispatch/assignments/{assignment_id}",
            headers=employee_headers,
        ),
        client.get(
            f"/api/v1/claims/assignments/{assignment_id}",
            headers=employee_headers,
        ),
    ]

    assert [response.status_code for response in responses] == [403, 403, 403]


def test_employee_cannot_read_unassigned_same_company_legacy_details(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        owner = db.scalar(select(User).where(User.username == "franchise_demo"))
        operator = db.scalar(select(User).where(User.username == "operation"))
        assert company is not None and owner is not None and operator is not None

        target_lead = _lead(name="同公司其他员工客户", phone="13900139102")
        db.add(target_lead)
        db.flush()
        target_assignment = _assignment(
            lead=target_lead,
            company=company,
            assigned_by=operator.id,
            internal_assignee_user_id=owner.id,
        )
        db.add(target_assignment)
        db.commit()
        lead_id = target_lead.id
        assignment_id = target_assignment.id

    employee_headers = _login(client, "franchise_employee_demo", "Employee123!")
    responses = [
        client.get(f"/api/v1/leads/{lead_id}", headers=employee_headers),
        client.get(
            f"/api/v1/dispatch/assignments/{assignment_id}",
            headers=employee_headers,
        ),
        client.get(
            f"/api/v1/claims/assignments/{assignment_id}",
            headers=employee_headers,
        ),
    ]

    assert [response.status_code for response in responses] == [403, 403, 403]

    owner_headers = _login(client, "franchise_demo", "Franchise123!")
    assert client.get(f"/api/v1/leads/{lead_id}", headers=owner_headers).status_code == 200
    assert (
        client.get(
            f"/api/v1/dispatch/assignments/{assignment_id}",
            headers=owner_headers,
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/claims/assignments/{assignment_id}",
            headers=owner_headers,
        ).status_code
        == 200
    )


def test_legacy_assignment_list_remains_forbidden_to_employee(api_client) -> None:
    client, _factory = api_client
    employee_headers = _login(client, "franchise_employee_demo", "Employee123!")

    response = client.get("/api/v1/dispatch/assignments", headers=employee_headers)

    assert response.status_code == 403


def test_telesales_cannot_read_unassigned_legacy_lead(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        lead = _lead(name="未分配给电销的客户", phone="13900139103")
        db.add(lead)
        db.commit()
        lead_id = lead.id

    telesales_headers = _login(client, "telesales", "Telesales123!")
    response = client.get(f"/api/v1/leads/{lead_id}", headers=telesales_headers)

    assert response.status_code == 403
    assert "13900139103" not in response.text


def test_owner_pending_claim_legacy_lead_keeps_phone_masked(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        owner = db.scalar(select(User).where(User.username == "franchise_demo"))
        operator = db.scalar(select(User).where(User.username == "operation"))
        assert company is not None and owner is not None and operator is not None

        lead = _lead(name="待领取客户", phone="13900139104")
        lead.status = AssignmentStatus.PENDING_CLAIM.value
        db.add(lead)
        db.flush()
        assignment = _assignment(
            lead=lead,
            company=company,
            assigned_by=operator.id,
            internal_assignee_user_id=owner.id,
            status=AssignmentStatus.PENDING_CLAIM.value,
        )
        db.add(assignment)
        db.flush()
        lead.current_assignment_id = assignment.id
        db.commit()
        lead_id = lead.id

    owner_headers = _login(client, "franchise_demo", "Franchise123!")
    response = client.get(f"/api/v1/leads/{lead_id}", headers=owner_headers)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["phone"] is None
    assert data["phone_masked"] == "139****9104"

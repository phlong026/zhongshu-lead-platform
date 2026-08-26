from __future__ import annotations

from sqlalchemy import select

from apps.api.src.core.models import Assignment, AuditLog, Company, Lead, User


def _data(response):
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def _create_empty_company(client, headers: dict[str, str], name: str) -> dict:
    return _data(
        client.post(
            "/api/v1/companies/simple",
            headers=headers,
            json={
                "name": name,
                "owner_name": "测试负责人",
                "primary_city_code": "310000",
                "district_codes": ["310115"],
                "serve_all_districts": False,
            },
        )
    )


def test_operation_can_disable_and_enable_a_franchise_company(api_client) -> None:
    client, factory = api_client
    operation = _login(client, "operation", "Operation123!")
    company = _create_empty_company(client, operation, "生命周期测试加盟商")

    disabled = client.post(
        f"/api/v1/companies/{company['id']}/disable",
        headers=operation,
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["data"]["status"] == "DISABLED"

    with factory() as db:
        stored = db.get(Company, company["id"])
        assert stored is not None
        assert stored.status == "DISABLED"
        assert db.scalar(
            select(AuditLog).where(
                AuditLog.action == "COMPANY_DISABLE",
                AuditLog.resource_id == company["id"],
            )
        )

    enabled = client.post(
        f"/api/v1/companies/{company['id']}/enable",
        headers=operation,
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["data"]["status"] == "ACTIVE"


def test_superadmin_can_delete_an_empty_test_company(api_client) -> None:
    client, _ = api_client
    admin = _login(client, "admin", "Admin123!")
    company = _create_empty_company(client, admin, "管理员可删除测试主体")

    deleted = client.request(
        "DELETE",
        f"/api/v1/companies/{company['id']}",
        headers=admin,
        json={"confirmation_code": company["code"]},
    )
    assert deleted.status_code == 200, deleted.text


def test_company_with_bound_person_cannot_be_deleted(api_client) -> None:
    client, factory = api_client
    operation = _login(client, "operation", "Operation123!")
    company = _create_empty_company(client, operation, "绑定人员加盟商")

    with factory() as db:
        franchise_user = db.scalar(select(User).where(User.username == "franchise_demo"))
        assert franchise_user is not None
        franchise_user.company_id = company["id"]
        db.commit()

    company_page = _data(client.get("/api/v1/companies?page=1&page_size=20", headers=operation))
    listed = next(item for item in company_page["items"] if item["id"] == company["id"])
    assert listed["can_delete"] is False

    rejected = client.request(
        "DELETE",
        f"/api/v1/companies/{company['id']}",
        headers=operation,
        json={"confirmation_code": company["code"]},
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "COMPANY_DELETE_BLOCKED"


def test_only_empty_unbound_test_company_can_be_deleted_after_code_confirmation(api_client) -> None:
    client, factory = api_client
    operation = _login(client, "operation", "Operation123!")
    company = _create_empty_company(client, operation, "可删除测试加盟商")

    company_page = _data(client.get("/api/v1/companies?page=1&page_size=20", headers=operation))
    listed = next(item for item in company_page["items"] if item["id"] == company["id"])
    assert listed["can_delete"] is True

    wrong_confirmation = client.request(
        "DELETE",
        f"/api/v1/companies/{company['id']}",
        headers=operation,
        json={"confirmation_code": "WRONG-CODE"},
    )
    assert wrong_confirmation.status_code == 400
    assert wrong_confirmation.json()["code"] == "COMPANY_DELETE_CONFIRMATION_INVALID"

    deleted = client.request(
        "DELETE",
        f"/api/v1/companies/{company['id']}",
        headers=operation,
        json={"confirmation_code": company["code"]},
    )
    assert deleted.status_code == 200, deleted.text

    with factory() as db:
        assert db.get(Company, company["id"]) is None
        assert db.scalar(
            select(AuditLog).where(
                AuditLog.action == "COMPANY_DELETE",
                AuditLog.resource_id == company["id"],
            )
        )


def test_company_with_assignment_history_can_only_be_disabled(api_client) -> None:
    client, factory = api_client
    operation = _login(client, "operation", "Operation123!")
    company = _create_empty_company(client, operation, "经营中加盟商")

    with factory() as db:
        operator = db.scalar(select(User).where(User.username == "operation"))
        assert operator is not None
        lead = Lead(
            customer_name="历史客户",
            phone_encrypted="test-encrypted-phone",
            phone_hash="test-phone-hash",
            region_code="310115",
            category_code="OLD_RENOVATION",
            status="READY_DISPATCH",
        )
        db.add(lead)
        db.flush()
        db.add(
            Assignment(
                lead_id=lead.id,
                company_id=company["id"],
                status="PENDING_CLAIM",
                points_price=100,
                assigned_by=operator.id,
            )
        )
        db.commit()

    rejected = client.request(
        "DELETE",
        f"/api/v1/companies/{company['id']}",
        headers=operation,
        json={"confirmation_code": company["code"]},
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "COMPANY_DELETE_BLOCKED"

    disabled = client.post(
        f"/api/v1/companies/{company['id']}/disable",
        headers=operation,
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["data"]["status"] == "DISABLED"

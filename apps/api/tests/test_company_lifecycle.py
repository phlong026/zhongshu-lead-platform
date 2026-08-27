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
                "is_test": True,
            },
        )
    )


def test_operation_can_disable_and_enable_a_franchise_company(api_client) -> None:
    client, factory = api_client
    operation = _login(client, "operation", "Operation123!")
    company = _create_empty_company(client, operation, "生命周期测试加盟商")

    disabled = client.patch(
        f"/api/v1/companies/{company['id']}",
        headers=operation,
        json={"status": "DISABLED", "reason": "暂停合作"},
    )
    assert disabled.status_code == 200, disabled.text

    with factory() as db:
        stored = db.get(Company, company["id"])
        assert stored is not None
        assert stored.status == "DISABLED"
        assert db.scalar(
            select(AuditLog).where(
                AuditLog.action == "COMPANY_UPDATE",
                AuditLog.resource_id == company["id"],
            )
        )

    enabled = client.patch(
        f"/api/v1/companies/{company['id']}",
        headers=operation,
        json={"status": "ACTIVE", "reason": "恢复合作"},
    )
    assert enabled.status_code == 200, enabled.text
    with factory() as db:
        stored = db.get(Company, company["id"])
        assert stored is not None and stored.status == "ACTIVE"


def test_superadmin_can_delete_an_empty_test_company(api_client) -> None:
    client, _ = api_client
    admin = _login(client, "admin", "Admin123!")
    company = _create_empty_company(client, admin, "管理员可删除测试主体")
    disabled = client.patch(
        f"/api/v1/companies/{company['id']}",
        headers=admin,
        json={"status": "DISABLED", "reason": "清理联测主体"},
    )
    assert disabled.status_code == 200, disabled.text

    deleted = client.request(
        "DELETE",
        f"/api/v1/companies/{company['id']}",
        headers=admin,
        json={"confirm_name": company["name"], "reason": "清理联测主体"},
    )
    assert deleted.status_code == 200, deleted.text


def test_active_company_cannot_be_deleted(api_client) -> None:
    client, _ = api_client
    operation = _login(client, "operation", "Operation123!")
    company = _create_empty_company(client, operation, "未停用测试加盟商")

    rejected = client.request(
        "DELETE",
        f"/api/v1/companies/{company['id']}",
        headers=operation,
        json={"confirm_name": company["name"], "reason": "尝试跳过停用"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "COMPANY_MUST_BE_DISABLED"


def test_only_empty_test_company_can_be_deleted_after_name_confirmation(api_client) -> None:
    client, factory = api_client
    operation = _login(client, "operation", "Operation123!")
    company = _create_empty_company(client, operation, "可删除测试加盟商")
    disabled = client.patch(
        f"/api/v1/companies/{company['id']}",
        headers=operation,
        json={"status": "DISABLED", "reason": "清理联测主体"},
    )
    assert disabled.status_code == 200, disabled.text

    wrong_confirmation = client.request(
        "DELETE",
        f"/api/v1/companies/{company['id']}",
        headers=operation,
        json={"confirm_name": "错误名称", "reason": "清理联测主体"},
    )
    assert wrong_confirmation.status_code == 409
    assert wrong_confirmation.json()["code"] == "COMPANY_CONFIRMATION_MISMATCH"

    deleted = client.request(
        "DELETE",
        f"/api/v1/companies/{company['id']}",
        headers=operation,
        json={"confirm_name": company["name"], "reason": "清理联测主体"},
    )
    assert deleted.status_code == 200, deleted.text

    with factory() as db:
        assert db.get(Company, company["id"]) is None
        assert db.scalar(
            select(AuditLog).where(
                AuditLog.action == "COMPANY_TEST_DELETE",
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

    disabled = client.patch(
        f"/api/v1/companies/{company['id']}",
        headers=operation,
        json={"status": "DISABLED", "reason": "核对历史业务"},
    )
    assert disabled.status_code == 200, disabled.text

    rejected = client.request(
        "DELETE",
        f"/api/v1/companies/{company['id']}",
        headers=operation,
        json={"confirm_name": company["name"], "reason": "尝试清理有业务主体"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "COMPANY_DELETE_BLOCKED"

    enabled = client.patch(
        f"/api/v1/companies/{company['id']}",
        headers=operation,
        json={"status": "ACTIVE", "reason": "继续保留业务主体"},
    )
    assert enabled.status_code == 200, enabled.text

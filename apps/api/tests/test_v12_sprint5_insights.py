from __future__ import annotations

from sqlalchemy import select

from apps.api.src.core.models import AuditLog


def login(client, username: str, password: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    client.headers.update({"Authorization": f"Bearer {token}"})


def _contains_key(value, names: set[str]) -> bool:
    if isinstance(value, dict):
        return any(key in names or _contains_key(item, names) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_key(item, names) for item in value)
    return False


def test_superadmin_can_read_v12_overview_and_audit(api_client):
    client, _factory = api_client
    login(client, "admin", "Admin123!")

    report = client.get("/api/v1/v1.2/reports/overview")
    assert report.status_code == 200, report.text
    data = report.json()["data"]
    assert {"leads", "assignments", "returns", "supplier_rewards", "points_ledger"} <= set(data)

    audit = client.get("/api/v1/v1.2/audit-events?page=1&page_size=20")
    assert audit.status_code == 200, audit.text
    assert {"items", "total", "page", "page_size"} <= set(audit.json()["data"])


def test_operation_can_read_report_and_audit_after_sprint5_rbac(api_client):
    client, _factory = api_client
    login(client, "operation", "Operation123!")

    assert client.get("/api/v1/v1.2/reports/overview").status_code == 200
    assert client.get("/api/v1/v1.2/audit-events").status_code == 200


def test_audit_events_expose_the_business_operator_name(api_client):
    client, _factory = api_client
    login(client, "operation", "Operation123!")

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    display_name = me.json()["data"]["display_name"]
    response = client.get("/api/v1/v1.2/audit-events?page=1&page_size=50")

    assert response.status_code == 200, response.text
    events = response.json()["data"]["items"]
    own_login = next(item for item in events if item["action"] == "AUTH_LOGIN")
    assert own_login["actor_name"] == display_name


def test_operation_overview_hides_financial_projection(api_client):
    client, _factory = api_client
    login(client, "operation", "Operation123!")

    response = client.get("/api/v1/v1.2/reports/overview")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert "points_ledger" not in data
    assert not _contains_key(data, {"net_delta", "balance", "recharge", "income", "revenue"})


def test_superadmin_overview_keeps_points_ledger_projection(api_client):
    client, _factory = api_client
    login(client, "admin", "Admin123!")

    response = client.get("/api/v1/v1.2/reports/overview")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert {"count", "net_delta"} <= set(data["points_ledger"])


def test_management_overview_exposes_business_pool_verification_and_risk_counts(api_client):
    client, _factory = api_client
    login(client, "admin", "Admin123!")

    response = client.get("/api/v1/v1.2/reports/overview")

    assert response.status_code == 200, response.text
    management = response.json()["data"]["management"]
    assert {"lead_pool", "verification", "exceptions"} <= set(management)
    assert {"total", "unassigned", "dispatching", "problem"} <= set(management["lead_pool"])
    assert {"pending", "in_progress", "awaiting_operation", "overdue"} <= set(management["verification"])


def test_operation_can_update_a_franchise_company_profile(api_client):
    client, _factory = api_client
    login(client, "operation", "Operation123!")

    companies = client.get("/api/v1/companies?page=1&page_size=1")
    assert companies.status_code == 200, companies.text
    company = companies.json()["data"]["items"][0]

    response = client.patch(
        f"/api/v1/companies/{company['id']}",
        json={"owner_name": "运营更新负责人"},
    )

    assert response.status_code == 200, response.text


def test_platform_user_can_change_own_password_and_keep_current_session(api_client):
    client, _factory = api_client
    login(client, "operation", "Operation123!")

    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Operation123!", "new_password": "Operation456!"},
    )

    assert response.status_code == 200, response.text
    client.headers.pop("Authorization", None)
    assert client.get("/api/v1/auth/me").status_code == 200

    old_password_login = client.post(
        "/api/v1/auth/login",
        json={"username": "operation", "password": "Operation123!"},
    )
    assert old_password_login.status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "operation", "password": "Operation456!"},
    ).status_code == 200


def test_platform_user_can_change_own_username_and_keep_current_session(api_client):
    client, factory = api_client
    login(client, "operation", "Operation123!")

    response = client.post(
        "/api/v1/auth/change-username",
        json={"current_password": "Operation123!", "username": "operation-renamed"},
    )

    assert response.status_code == 200, response.text
    client.headers.pop("Authorization", None)
    assert client.get("/api/v1/auth/me").json()["data"]["username"] == "operation-renamed"
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "operation", "password": "Operation123!"},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "operation-renamed", "password": "Operation123!"},
    ).status_code == 200

    with factory() as db:
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "AUTH_USERNAME_CHANGE").order_by(AuditLog.created_at.desc())
        )
        assert audit is not None
        assert audit.before_json == {"username": "operation"}
        assert audit.after_json == {"username": "operation-renamed"}


def test_franchise_has_company_report_but_not_platform_overview(api_client):
    client, _factory = api_client
    login(client, "franchise_demo", "Franchise123!")

    own = client.get("/api/v1/v1.2/reports/own")
    assert own.status_code == 200, own.text
    assert own.json()["data"]["company_id"]

    overview = client.get("/api/v1/v1.2/reports/overview")
    assert overview.status_code == 403


def test_trace_returns_not_found_for_unknown_business_id(api_client):
    client, _factory = api_client
    login(client, "admin", "Admin123!")
    response = client.get("/api/v1/v1.2/trace/unknown-business-id")
    assert response.status_code == 404
    assert response.json()["code"] == "BUSINESS_TRACE_NOT_FOUND"

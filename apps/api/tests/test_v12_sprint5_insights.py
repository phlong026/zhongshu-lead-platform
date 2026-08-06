from __future__ import annotations


def login(client, username: str, password: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text


def test_owner_can_read_v12_overview_and_audit(api_client):
    client, _factory = api_client
    login(client, "owner", "Owner123!")

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
    login(client, "owner", "Owner123!")
    response = client.get("/api/v1/v1.2/trace/unknown-business-id")
    assert response.status_code == 404
    assert response.json()["code"] == "BUSINESS_TRACE_NOT_FOUND"

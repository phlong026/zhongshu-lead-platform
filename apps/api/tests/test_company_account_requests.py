from __future__ import annotations

from sqlalchemy import select

from apps.api.src.core.models import AuditLog


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


def _create_company(client, admin: dict[str, str]) -> str:
    return _data(
        client.post(
            "/api/v1/companies/simple",
            headers=admin,
            json={
                "name": "人员申请验收加盟商",
                "owner_name": "张负责人",
                "primary_city_code": "310000",
                "serve_all_districts": True,
            },
        )
    )["id"]


def _create_company_account(
    client,
    operation: dict[str, str],
    company_id: str,
    *,
    username: str,
    display_name: str,
    role_code: str,
) -> dict[str, object]:
    return _data(
        client.post(
            f"/api/v1/companies/{company_id}/accounts",
            headers=operation,
            json={
                "username": username,
                "password": "simple88",
                "display_name": display_name,
                "role_code": role_code,
            },
        )
    )


def test_owner_submits_employee_requests_and_operation_executes_without_exposing_passwords(
    api_client,
) -> None:
    client, factory = api_client
    admin = _login(client, "admin", "Admin123!")
    operation = _login(client, "operation", "Operation123!")
    company_id = _create_company(client, admin)
    owner = _create_company_account(
        client,
        operation,
        company_id,
        username="request_owner",
        display_name="申请负责人",
        role_code="FRANCHISE_OWNER",
    )
    existing_employee = _create_company_account(
        client,
        operation,
        company_id,
        username="request_existing_employee",
        display_name="现有员工",
        role_code="FRANCHISE_EMPLOYEE",
    )
    owner_session = _login(client, "request_owner", "simple88")
    employee_session = _login(client, "request_existing_employee", "simple88")

    directory = _data(
        client.get(
            f"/api/v1/companies/{company_id}/account-directory",
            headers=owner_session,
        )
    )
    assert [(item["username"], item["role_code"]) for item in directory] == [
        ("request_owner", "FRANCHISE_OWNER"),
        ("request_existing_employee", "FRANCHISE_EMPLOYEE"),
    ]
    assert all("password" not in str(item).lower() for item in directory)
    assert all("session_version" not in item for item in directory)

    direct_create = client.post(
        f"/api/v1/companies/{company_id}/accounts",
        headers=owner_session,
        json={
            "username": "owner_should_not_create",
            "display_name": "越权员工",
            "role_code": "FRANCHISE_EMPLOYEE",
        },
    )
    assert direct_create.status_code == 403

    create_request = _data(
        client.post(
            f"/api/v1/companies/{company_id}/account-requests",
            headers=owner_session,
            json={
                "request_type": "CREATE_EMPLOYEE",
                "username": "request_new_employee",
                "display_name": "待开通员工",
                "reason": "门店新增销售人员，需要使用客资工作台",
            },
        )
    )
    assert create_request["status"] == "PENDING"
    assert create_request["requested_by"] == owner["id"]
    assert "initial_password" not in create_request

    approved_create = _data(
        client.post(
            f"/api/v1/companies/{company_id}/account-requests/{create_request['id']}/approve",
            headers=operation,
            json={"reason": "运营核实新增人员申请后执行开户"},
        )
    )
    assert approved_create["status"] == "APPROVED"
    assert approved_create["executed_account"]["role_code"] == "FRANCHISE_EMPLOYEE"
    assert len(approved_create["initial_password"]) == 8
    assert approved_create["initial_password"].isalnum()

    disable_request = _data(
        client.post(
            f"/api/v1/companies/{company_id}/account-requests",
            headers=owner_session,
            json={
                "request_type": "DISABLE_EMPLOYEE",
                "target_user_id": existing_employee["id"],
                "reason": "员工已离职，申请停止系统访问",
            },
        )
    )
    approved_disable = _data(
        client.post(
            f"/api/v1/companies/{company_id}/account-requests/{disable_request['id']}/approve",
            headers=operation,
            json={"reason": "运营核实离职信息后执行停用"},
        )
    )
    assert approved_disable["status"] == "APPROVED"
    assert approved_disable["executed_account"]["status"] == "DISABLED"
    assert client.get("/api/v1/auth/me", headers=employee_session).status_code == 401

    owner_requests = _data(
        client.get(
            f"/api/v1/companies/{company_id}/account-requests",
            headers=owner_session,
        )
    )
    assert [item["status"] for item in owner_requests] == ["APPROVED", "APPROVED"]
    assert all("initial_password" not in item for item in owner_requests)

    with factory() as db:
        request_audits = db.scalars(
            select(AuditLog)
            .where(
                AuditLog.company_id == company_id,
                AuditLog.action.in_(
                    {
                        "COMPANY_ACCOUNT_REQUEST_CREATE",
                        "COMPANY_ACCOUNT_REQUEST_APPROVE",
                    }
                ),
            )
            .order_by(AuditLog.created_at.asc())
        ).all()
        assert [item.action for item in request_audits] == [
            "COMPANY_ACCOUNT_REQUEST_CREATE",
            "COMPANY_ACCOUNT_REQUEST_APPROVE",
            "COMPANY_ACCOUNT_REQUEST_CREATE",
            "COMPANY_ACCOUNT_REQUEST_APPROVE",
        ]
        assert request_audits[0].actor_user_id == owner["id"]
        assert request_audits[1].actor_user_id != owner["id"]
        assert all("password" not in str(item.metadata_json).lower() for item in request_audits)


def test_account_request_rejection_and_company_scope_leave_no_account_change(api_client) -> None:
    client, _ = api_client
    admin = _login(client, "admin", "Admin123!")
    operation = _login(client, "operation", "Operation123!")
    company_id = _create_company(client, admin)
    other_company_id = _data(
        client.post(
            "/api/v1/companies/simple",
            headers=admin,
            json={
                "name": "其他公司",
                "owner_name": "李负责人",
                "primary_city_code": "310000",
                "serve_all_districts": True,
            },
        )
    )["id"]
    _create_company_account(
        client,
        operation,
        company_id,
        username="scope_owner",
        display_name="范围负责人",
        role_code="FRANCHISE_OWNER",
    )
    owner_session = _login(client, "scope_owner", "simple88")

    out_of_scope = client.post(
        f"/api/v1/companies/{other_company_id}/account-requests",
        headers=owner_session,
        json={
            "request_type": "CREATE_EMPLOYEE",
            "username": "scope_should_fail",
            "display_name": "越权员工",
            "reason": "不应允许跨公司申请",
        },
    )
    assert out_of_scope.status_code == 403

    pending = _data(
        client.post(
            f"/api/v1/companies/{company_id}/account-requests",
            headers=owner_session,
            json={
                "request_type": "CREATE_EMPLOYEE",
                "username": "rejected_employee",
                "display_name": "待驳回员工",
                "reason": "等待运营核验员工资料",
            },
        )
    )
    duplicate = client.post(
        f"/api/v1/companies/{company_id}/account-requests",
        headers=owner_session,
        json={
            "request_type": "CREATE_EMPLOYEE",
            "username": "rejected_employee",
            "display_name": "待驳回员工",
            "reason": "重复申请",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "COMPANY_ACCOUNT_REQUEST_PENDING"

    rejected = _data(
        client.post(
            f"/api/v1/companies/{company_id}/account-requests/{pending['id']}/reject",
            headers=operation,
            json={"reason": "申请资料不完整，请补充劳动关系说明"},
        )
    )
    assert rejected["status"] == "REJECTED"
    assert rejected["decision_reason"] == "申请资料不完整，请补充劳动关系说明"
    assert "executed_account" not in rejected

    directory = _data(
        client.get(
            f"/api/v1/companies/{company_id}/account-directory",
            headers=owner_session,
        )
    )
    assert [item["username"] for item in directory] == ["scope_owner"]


def test_stale_disable_request_cannot_be_marked_as_executed(api_client) -> None:
    client, _ = api_client
    admin = _login(client, "admin", "Admin123!")
    operation = _login(client, "operation", "Operation123!")
    company_id = _create_company(client, admin)
    _create_company_account(
        client,
        operation,
        company_id,
        username="stale_owner",
        display_name="时序负责人",
        role_code="FRANCHISE_OWNER",
    )
    employee = _create_company_account(
        client,
        operation,
        company_id,
        username="stale_employee",
        display_name="时序员工",
        role_code="FRANCHISE_EMPLOYEE",
    )
    owner_session = _login(client, "stale_owner", "simple88")

    pending = _data(
        client.post(
            f"/api/v1/companies/{company_id}/account-requests",
            headers=owner_session,
            json={
                "request_type": "DISABLE_EMPLOYEE",
                "target_user_id": employee["id"],
                "reason": "负责人申请停用离职员工",
            },
        )
    )
    _data(
        client.post(
            f"/api/v1/companies/{company_id}/accounts/{employee['id']}/disable",
            headers=operation,
            json={},
        )
    )

    stale_approval = client.post(
        f"/api/v1/companies/{company_id}/account-requests/{pending['id']}/approve",
        headers=operation,
        json={"reason": "运营准备执行停用申请"},
    )
    assert stale_approval.status_code == 409
    assert stale_approval.json()["code"] == "COMPANY_ACCOUNT_REQUEST_TARGET_DISABLED"

    requests = _data(
        client.get(
            f"/api/v1/companies/{company_id}/account-requests",
            headers=owner_session,
        )
    )
    assert requests[0]["status"] == "PENDING"

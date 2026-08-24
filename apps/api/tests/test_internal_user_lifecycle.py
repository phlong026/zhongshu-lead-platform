from __future__ import annotations

from sqlalchemy import select

from apps.api.src.core.models import AuditLog, User
from apps.api.src.core.security import verify_password


STRONG_PASSWORD = "Internal-User9!"
NEW_STRONG_PASSWORD = "Changed-User8!"


def _login(client, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    return token


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _data(response):
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["code"] == "OK"
    return payload["data"]


def _create_user(
    client,
    admin_token: str,
    *,
    username: str,
    password: str = STRONG_PASSWORD,
    role_codes: list[str] | None = None,
):
    return client.post(
        "/api/v1/users",
        headers=_bearer(admin_token),
        json={
            "username": username,
            "password": password,
            "display_name": f"{username} 测试账号",
            "role_codes": role_codes or ["OPERATION"],
        },
    )


def _user_by_username(factory, username: str) -> User:
    with factory() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        # Detach the complete state used by assertions below.
        _ = [role.code for role in user.roles]
        db.expunge(user)
        return user


def _audit_text(factory, user_id: str) -> tuple[list[str], str]:
    with factory() as db:
        audits = db.scalars(
            select(AuditLog)
            .where(AuditLog.resource_id == user_id)
            .order_by(AuditLog.created_at)
        ).all()
        return [audit.action for audit in audits], "\n".join(
            str(
                {
                    "before": audit.before_json,
                    "after": audit.after_json,
                    "metadata": audit.metadata_json,
                }
            )
            for audit in audits
        )


def test_superadmin_lists_only_internal_accounts(api_client) -> None:
    client, _ = api_client
    admin_token = _login(client, "admin", "Admin123!")

    users = _data(client.get("/api/v1/users", headers=_bearer(admin_token)))

    assert users
    assert all(user["company_id"] is None for user in users)
    assert all("FRANCHISE_OWNER" not in user["roles"] for user in users)
    assert "franchise_demo" not in {user["username"] for user in users}


def test_superadmin_creates_a_multi_role_internal_account_and_audits_it(api_client) -> None:
    client, factory = api_client
    admin_token = _login(client, "admin", "Admin123!")

    response = _create_user(
        client,
        admin_token,
        username="multi_role",
        role_codes=["LEAD_ENTRY", "OPERATION"],
    )
    user_id = _data(response)["id"]

    user = _user_by_username(factory, "multi_role")
    assert user.id == user_id
    assert user.company_id is None
    assert user.status == "ACTIVE"
    assert user.session_version == 1
    assert sorted(role.code for role in user.roles) == ["LEAD_ENTRY", "OPERATION"]
    assert verify_password(STRONG_PASSWORD, user.password_hash or "")

    actions, audit_text = _audit_text(factory, user.id)
    assert "USER_CREATE" in actions
    assert STRONG_PASSWORD not in audit_text
    assert (user.password_hash or "") not in audit_text


def test_create_generates_initial_password_when_password_is_omitted(api_client) -> None:
    client, factory = api_client
    admin_token = _login(client, "admin", "Admin123!")

    response = client.post(
        "/api/v1/users",
        headers=_bearer(admin_token),
        json={
            "username": "generated_password",
            "display_name": "自动密码测试账号",
            "role_codes": ["OPERATION"],
        },
    )

    data = _data(response)
    initial_password = data["initial_password"]
    assert data["username"] == "generated_password"
    assert isinstance(initial_password, str)
    assert 12 <= len(initial_password) <= 128
    assert any(character.islower() for character in initial_password)
    assert any(character.isupper() for character in initial_password)
    assert any(character.isdigit() for character in initial_password)
    assert any(not character.isalnum() for character in initial_password)
    assert "generated_password" not in initial_password.lower()
    assert response.headers["cache-control"] == "no-store"

    user = _user_by_username(factory, "generated_password")
    assert verify_password(initial_password, user.password_hash or "")
    assert _login(client, "generated_password", initial_password)

    _, audit_text = _audit_text(factory, user.id)
    assert initial_password not in audit_text
    assert (user.password_hash or "") not in audit_text


def test_generated_password_rejects_whitespace_only_username(api_client) -> None:
    client, _ = api_client
    admin_token = _login(client, "admin", "Admin123!")

    response = client.post(
        "/api/v1/users",
        headers=_bearer(admin_token),
        json={
            "username": "  ",
            "display_name": "空账号测试",
            "role_codes": ["OPERATION"],
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INTERNAL_IDENTITY_INVALID"
    assert response.json()["message"] == "登录账号不能为空或包含首尾空格"


def test_create_keeps_legacy_single_role_contract(api_client) -> None:
    client, factory = api_client
    admin_token = _login(client, "admin", "Admin123!")

    response = client.post(
        "/api/v1/users",
        headers=_bearer(admin_token),
        json={
            "username": "legacy_single_role",
            "password": STRONG_PASSWORD,
            "display_name": "旧单角色请求兼容",
            "role_code": "OPERATION",
        },
    )

    data = _data(response)
    assert "initial_password" not in data
    user = _user_by_username(factory, "legacy_single_role")
    assert [role.code for role in user.roles] == ["OPERATION"]


def test_create_rejects_ambiguous_old_and_new_role_fields(api_client) -> None:
    client, factory = api_client
    admin_token = _login(client, "admin", "Admin123!")

    response = client.post(
        "/api/v1/users",
        headers=_bearer(admin_token),
        json={
            "username": "ambiguous_roles",
            "password": STRONG_PASSWORD,
            "display_name": "角色字段冲突",
            "role_code": "OPERATION",
            "role_codes": ["OPERATION"],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["message"] == "请求参数校验失败"
    assert STRONG_PASSWORD not in response.text
    with factory() as db:
        assert db.scalar(select(User).where(User.username == "ambiguous_roles")) is None


def test_internal_account_creation_rejects_franchise_company_and_weak_passwords(api_client) -> None:
    client, factory = api_client
    admin_token = _login(client, "admin", "Admin123!")
    with factory() as db:
        franchise = db.scalar(select(User).where(User.username == "franchise_demo"))
        assert franchise is not None and franchise.company_id
        company_id = franchise.company_id

    franchise_role = _create_user(
        client,
        admin_token,
        username="invalid_franchise_role",
        role_codes=["FRANCHISE_OWNER"],
    )
    assert franchise_role.status_code == 400
    assert franchise_role.json()["code"] == "INTERNAL_ROLE_INVALID"

    company_bound = client.post(
        "/api/v1/users",
        headers=_bearer(admin_token),
        json={
            "username": "invalid_company_bound",
            "password": STRONG_PASSWORD,
            "display_name": "错误公司账号",
            "role_codes": ["OPERATION"],
            "company_id": company_id,
        },
    )
    assert company_bound.status_code == 400
    assert company_bound.json()["code"] == "INTERNAL_COMPANY_FORBIDDEN"

    weak_password = _create_user(
        client,
        admin_token,
        username="weak_password",
        password="password1234",
    )
    assert weak_password.status_code == 400
    assert weak_password.json()["code"] == "PASSWORD_POLICY_INVALID"


def test_non_superadmin_cannot_manage_internal_accounts(api_client) -> None:
    client, _ = api_client
    operation_token = _login(client, "operation", "Operation123!")

    assert client.get("/api/v1/users", headers=_bearer(operation_token)).status_code == 403
    assert _create_user(client, operation_token, username="forbidden_user").status_code == 403


def test_role_update_invalidates_existing_session_and_records_before_after(api_client) -> None:
    client, factory = api_client
    admin_token = _login(client, "admin", "Admin123!")
    user_id = _data(_create_user(client, admin_token, username="role_change"))["id"]
    old_token = _login(client, "role_change", STRONG_PASSWORD)
    before = _user_by_username(factory, "role_change")

    invalid = client.put(
        f"/api/v1/users/{user_id}/roles",
        headers=_bearer(admin_token),
        json={"role_codes": ["FRANCHISE_OWNER"]},
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "INTERNAL_ROLE_INVALID"

    response = client.put(
        f"/api/v1/users/{user_id}/roles",
        headers=_bearer(admin_token),
        json={"role_codes": ["RETURN_REVIEWER", "TELESALES"]},
    )
    _data(response)

    after = _user_by_username(factory, "role_change")
    assert after.session_version == before.session_version + 1
    assert sorted(role.code for role in after.roles) == ["RETURN_REVIEWER", "TELESALES"]
    expired = client.get("/api/v1/auth/me", headers=_bearer(old_token))
    assert expired.status_code == 401
    assert expired.json()["code"] == "AUTH_INVALID"
    new_token = _login(client, "role_change", STRONG_PASSWORD)
    me = _data(client.get("/api/v1/auth/me", headers=_bearer(new_token)))
    assert me["roles"] == ["RETURN_REVIEWER", "TELESALES"]

    _data(
        client.put(
            f"/api/v1/users/{user_id}/roles",
            headers=_bearer(admin_token),
            json={"role_codes": ["TELESALES", "RETURN_REVIEWER"]},
        )
    )
    unchanged = _user_by_username(factory, "role_change")
    assert unchanged.session_version == after.session_version

    actions, audit_text = _audit_text(factory, user_id)
    assert actions.count("USER_ROLES_UPDATE") == 1
    assert "OPERATION" in audit_text
    assert "RETURN_REVIEWER" in audit_text


def test_password_reset_invalidates_sessions_and_never_audits_credentials(api_client) -> None:
    client, factory = api_client
    admin_token = _login(client, "admin", "Admin123!")
    user_id = _data(_create_user(client, admin_token, username="password_reset"))["id"]
    old_token = _login(client, "password_reset", STRONG_PASSWORD)
    before = _user_by_username(factory, "password_reset")

    weak = client.post(
        f"/api/v1/users/{user_id}/reset-password",
        headers=_bearer(admin_token),
        json={"new_password": "weak-password"},
    )
    assert weak.status_code == 400
    assert weak.json()["code"] == "PASSWORD_POLICY_INVALID"

    _data(
        client.post(
            f"/api/v1/users/{user_id}/reset-password",
            headers=_bearer(admin_token),
            json={"new_password": NEW_STRONG_PASSWORD},
        )
    )

    after = _user_by_username(factory, "password_reset")
    assert after.session_version == before.session_version + 1
    assert client.get("/api/v1/auth/me", headers=_bearer(old_token)).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "password_reset", "password": STRONG_PASSWORD},
    ).status_code == 401
    assert _login(client, "password_reset", NEW_STRONG_PASSWORD)

    actions, audit_text = _audit_text(factory, user_id)
    assert "USER_PASSWORD_RESET" in actions
    assert STRONG_PASSWORD not in audit_text
    assert NEW_STRONG_PASSWORD not in audit_text
    assert (before.password_hash or "") not in audit_text
    assert (after.password_hash or "") not in audit_text


def test_disable_and_enable_are_idempotent_and_invalidate_sessions(api_client) -> None:
    client, factory = api_client
    admin_token = _login(client, "admin", "Admin123!")
    user_id = _data(_create_user(client, admin_token, username="toggle_user"))["id"]
    old_token = _login(client, "toggle_user", STRONG_PASSWORD)
    created = _user_by_username(factory, "toggle_user")

    _data(client.post(f"/api/v1/users/{user_id}/disable", headers=_bearer(admin_token)))
    disabled = _user_by_username(factory, "toggle_user")
    assert disabled.status == "DISABLED"
    assert disabled.session_version == created.session_version + 1
    assert client.get("/api/v1/auth/me", headers=_bearer(old_token)).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "toggle_user", "password": STRONG_PASSWORD},
    ).status_code == 401

    _data(client.post(f"/api/v1/users/{user_id}/disable", headers=_bearer(admin_token)))
    disabled_again = _user_by_username(factory, "toggle_user")
    assert disabled_again.session_version == disabled.session_version

    _data(client.post(f"/api/v1/users/{user_id}/enable", headers=_bearer(admin_token)))
    enabled = _user_by_username(factory, "toggle_user")
    assert enabled.status == "ACTIVE"
    assert enabled.session_version == disabled.session_version + 1
    assert _login(client, "toggle_user", STRONG_PASSWORD)

    _data(client.post(f"/api/v1/users/{user_id}/enable", headers=_bearer(admin_token)))
    enabled_again = _user_by_username(factory, "toggle_user")
    assert enabled_again.session_version == enabled.session_version

    actions, _ = _audit_text(factory, user_id)
    assert actions.count("USER_DISABLE") == 1
    assert actions.count("USER_ENABLE") == 1


def test_last_active_superadmin_cannot_be_disabled_or_demoted(api_client) -> None:
    client, factory = api_client
    admin_token = _login(client, "admin", "Admin123!")
    admin = _user_by_username(factory, "admin")

    disabled = client.post(
        f"/api/v1/users/{admin.id}/disable",
        headers=_bearer(admin_token),
    )
    assert disabled.status_code == 409
    assert disabled.json()["code"] == "LAST_SUPER_ADMIN_REQUIRED"

    demoted = client.put(
        f"/api/v1/users/{admin.id}/roles",
        headers=_bearer(admin_token),
        json={"role_codes": ["OWNER"]},
    )
    assert demoted.status_code == 409
    assert demoted.json()["code"] == "LAST_SUPER_ADMIN_REQUIRED"

    unchanged = _user_by_username(factory, "admin")
    assert unchanged.status == "ACTIVE"
    assert "SUPER_ADMIN" in {role.code for role in unchanged.roles}

    second_id = _data(
        _create_user(
            client,
            admin_token,
            username="second_superadmin",
            role_codes=["SUPER_ADMIN"],
        )
    )["id"]
    _data(
        client.put(
            f"/api/v1/users/{admin.id}/roles",
            headers=_bearer(admin_token),
            json={"role_codes": ["OWNER"]},
        )
    )
    first_after = _user_by_username(factory, "admin")
    assert "SUPER_ADMIN" not in {role.code for role in first_after.roles}
    assert client.get("/api/v1/auth/me", headers=_bearer(admin_token)).status_code == 401
    assert _user_by_username(factory, "second_superadmin").id == second_id


def test_franchise_and_missing_users_cannot_enter_internal_management(api_client) -> None:
    client, factory = api_client
    admin_token = _login(client, "admin", "Admin123!")
    with factory() as db:
        franchise = db.scalar(select(User).where(User.username == "franchise_demo"))
        assert franchise is not None
        franchise_id = franchise.id

    attempts = [
        client.put(
            f"/api/v1/users/{franchise_id}/roles",
            headers=_bearer(admin_token),
            json={"role_codes": ["OPERATION"]},
        ),
        client.post(f"/api/v1/users/{franchise_id}/disable", headers=_bearer(admin_token)),
        client.post(f"/api/v1/users/{franchise_id}/enable", headers=_bearer(admin_token)),
        client.post(
            f"/api/v1/users/{franchise_id}/reset-password",
            headers=_bearer(admin_token),
            json={"new_password": NEW_STRONG_PASSWORD},
        ),
    ]
    assert all(response.status_code == 409 for response in attempts)
    assert {response.json()["code"] for response in attempts} == {"INTERNAL_USER_REQUIRED"}

    missing = client.post(
        "/api/v1/users/missing-user/disable",
        headers=_bearer(admin_token),
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "USER_NOT_FOUND"

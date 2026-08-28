from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from apps.api.src.core.auth_models import AuthLoginState
from apps.api.src.core.models import AuditLog, Company, User
from apps.api.src.core.security import create_access_token, verify_password
from apps.api.src.services.auth_service import InternalAuthError, authenticate_internal
from apps.api.src.services.rbac import assign_role


def _login(client, username: str, password: str):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"user-agent": "hardening-test/1.0", "x-real-ip": "203.0.113.10"},
    )


def _failure_contract(response) -> tuple[int, str, str]:
    payload = response.json()
    return response.status_code, payload["code"], payload["message"]


def test_browser_login_uses_http_only_cookie_without_raw_jwt(api_client) -> None:
    client, _ = api_client
    response = _login(client, "admin", "Admin123!")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert "token" not in data
    assert data["user"]["display_name"]
    token = response.cookies.get("access_token")
    assert token
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "path=/" in set_cookie


def test_production_login_cookie_is_secure(api_client, monkeypatch) -> None:
    client, _ = api_client
    import apps.api.src.routers.auth as auth_router

    monkeypatch.setattr(auth_router.settings, "app_env", "production")
    response = _login(client, "admin", "Admin123!")
    assert response.status_code == 200, response.text
    set_cookie = response.headers["set-cookie"].lower()
    assert "secure" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie


def test_internal_login_failures_persist_lock_and_expire_with_audit(api_client) -> None:
    client, factory = api_client
    wrong_password = "Definitely-Wrong-Password!"
    generic = (401, "AUTH_LOGIN_FAILED", "用户名或密码错误")

    for _ in range(4):
        response = _login(client, "admin", wrong_password)
        assert _failure_contract(response) == generic

    locked = _login(client, "admin", wrong_password)
    assert _failure_contract(locked) == generic

    blocked_correct = _login(client, "admin", "Admin123!")
    assert _failure_contract(blocked_correct) == generic
    unknown = _login(client, "does-not-exist", "Arbitrary-Wrong-Password!")
    assert _failure_contract(unknown) == generic

    with factory() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        state = db.get(AuthLoginState, user.id)
        assert state is not None
        assert state.failed_count == 5
        assert state.locked_until is not None
        actions = db.scalars(select(AuditLog.action).where(AuditLog.resource_id == user.id)).all()
        assert actions.count("AUTH_LOGIN_FAILED") == 4
        assert "AUTH_LOGIN_LOCKED" in actions
        assert "AUTH_LOGIN_BLOCKED" in actions

        logs = db.scalars(select(AuditLog).where(AuditLog.resource_id == user.id)).all()
        serialized = "\n".join(
            str(
                {
                    "before": item.before_json,
                    "after": item.after_json,
                    "metadata": item.metadata_json,
                    "request_id": item.request_id,
                }
            )
            for item in logs
        )
        assert wrong_password not in serialized
        assert "Admin123!" not in serialized

        state.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    recovered = _login(client, "admin", "Admin123!")
    assert recovered.status_code == 200, recovered.text
    token = recovered.cookies.get("access_token")
    assert token and token not in recovered.text

    with factory() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        state = db.get(AuthLoginState, user.id)
        assert state is not None
        assert state.failed_count == 0
        assert state.last_failed_at is None
        assert state.locked_until is None
        actions = db.scalars(select(AuditLog.action).where(AuditLog.resource_id == user.id)).all()
        assert "AUTH_LOGIN_UNLOCKED" in actions
        assert "AUTH_LOGIN" in actions
        logs = db.scalars(select(AuditLog).where(AuditLog.resource_id == user.id)).all()
        serialized = "\n".join(str(item.metadata_json) for item in logs)
        assert token not in serialized


def test_sqlite_parallel_failed_logins_are_atomically_counted(api_client) -> None:
    _, factory = api_client

    def fail_once(index: int) -> str:
        with factory() as db:
            try:
                authenticate_internal(db, "admin", f"parallel-wrong-{index}!")
            except InternalAuthError as exc:
                db.commit()
                return exc.audit_action
            raise AssertionError("wrong password unexpectedly authenticated")

    with ThreadPoolExecutor(max_workers=5) as pool:
        actions = list(pool.map(fail_once, range(5)))

    with factory() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        state = db.get(AuthLoginState, user.id)
        assert state is not None
        assert state.failed_count == 5
        assert state.locked_until is not None
    assert actions.count("AUTH_LOGIN_FAILED") == 4
    assert actions.count("AUTH_LOGIN_LOCKED") == 1


def test_disabled_user_invalidates_existing_cookie_and_cannot_relogin(api_client) -> None:
    client, factory = api_client
    login = _login(client, "operation", "Operation123!")
    assert login.status_code == 200
    assert login.cookies.get("access_token")

    with factory() as db:
        user = db.scalar(select(User).where(User.username == "operation"))
        assert user is not None
        user.status = "DISABLED"
        db.commit()

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 401
    assert me.json()["code"] == "AUTH_INVALID"

    relogin = _login(client, "operation", "Operation123!")
    unknown = _login(client, "does-not-exist", "Arbitrary-Wrong-Password!")
    assert _failure_contract(relogin) == _failure_contract(unknown)
    assert _failure_contract(relogin) == (401, "AUTH_LOGIN_FAILED", "用户名或密码错误")


def test_disabled_company_account_is_rejected_before_a_cookie_is_issued(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        user = db.scalar(select(User).where(User.username == "franchise_demo"))
        assert user is not None and user.company_id
        company = db.get(Company, user.company_id)
        assert company is not None
        company.status = "DISABLED"
        db.commit()

    response = _login(client, "franchise_demo", "Franchise123!")

    assert _failure_contract(response) == (403, "AUTH_COMPANY_DISABLED", "加盟商已停用，暂时无法登录")
    assert response.cookies.get("access_token") is None


def test_disabled_user_consumes_expired_lock_only_once(api_client) -> None:
    client, factory = api_client
    generic = (401, "AUTH_LOGIN_FAILED", "用户名或密码错误")
    with factory() as db:
        user = db.scalar(select(User).where(User.username == "operation"))
        assert user is not None
        user.status = "DISABLED"
        state = db.get(AuthLoginState, user.id)
        if state is None:
            state = AuthLoginState(user_id=user.id)
            db.add(state)
        state.failed_count = 5
        state.last_failed_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        state.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        user_id = user.id

    first = _login(client, "operation", "Operation123!")
    second = _login(client, "operation", "Operation123!")
    assert _failure_contract(first) == generic
    assert _failure_contract(second) == generic

    with factory() as db:
        state = db.get(AuthLoginState, user_id)
        assert state is not None
        assert state.failed_count == 0
        assert state.last_failed_at is None
        assert state.locked_until is None
        actions = db.scalars(select(AuditLog.action).where(AuditLog.resource_id == user_id)).all()
        assert actions.count("AUTH_LOGIN_UNLOCKED") == 1
        assert actions.count("AUTH_LOGIN_BLOCKED") == 2


def test_logout_invalidates_previous_bearer_token_via_session_version(api_client) -> None:
    client, _ = api_client
    login = _login(client, "franchise_demo", "Franchise123!")
    assert login.status_code == 200
    token = login.cookies.get("access_token")
    assert token

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200

    old_token = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert old_token.status_code == 401
    assert old_token.json()["code"] == "AUTH_INVALID"


def test_password_change_invalidates_every_older_bearer_token(api_client) -> None:
    client, _ = api_client
    first_login = _login(client, "operation", "Operation123!")
    second_login = _login(client, "operation", "Operation123!")
    first_token = first_login.cookies.get("access_token")
    second_token = second_login.cookies.get("access_token")
    assert first_token and second_token

    changed = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Operation123!", "new_password": "Operation456!"},
        headers={"Authorization": f"Bearer {first_token}"},
    )

    assert changed.status_code == 200, changed.text
    current_token = changed.cookies.get("access_token")
    assert current_token
    for old_token in (first_token, second_token):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == "AUTH_INVALID"
    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {current_token}"},
    ).status_code == 200


def test_wechat_bound_owner_can_set_first_backup_password_without_current_password(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        company = Company(code="BACKUP-PWD", name="备用密码测试", status="ACTIVE")
        db.add(company)
        db.flush()
        user = User(
            username="backup_owner",
            display_name="备用密码负责人",
            company_id=company.id,
            status="ACTIVE",
            password_hash=None,
        )
        db.add(user)
        db.flush()
        company.primary_user_id = user.id
        assign_role(db, user, "FRANCHISE_OWNER")
        token = create_access_token(user.id, user.session_version, ["FRANCHISE_OWNER"], company.id)
        user_id = user.id
        db.commit()

    first_set = client.post(
        "/api/v1/auth/change-password",
        json={"new_password": "Backup888"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert first_set.status_code == 200, first_set.text
    assert first_set.json()["message"] == "备用登录密码已设置"

    with factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        assert verify_password("Backup888", user.password_hash or "")
        actions = db.scalars(select(AuditLog.action).where(AuditLog.resource_id == user_id)).all()
        assert "AUTH_BACKUP_PASSWORD_SET" in actions

    current_token = first_set.cookies.get("access_token")
    assert current_token
    second_set = client.post(
        "/api/v1/auth/change-password",
        json={"new_password": "Backup999"},
        headers={"Authorization": f"Bearer {current_token}"},
    )
    assert second_set.status_code == 422
    assert second_set.json()["code"] == "AUTH_CURRENT_PASSWORD_REQUIRED"


def test_change_username_returns_conflict_for_an_existing_login_name(api_client) -> None:
    client, _ = api_client
    login = _login(client, "operation", "Operation123!")
    token = login.cookies.get("access_token")
    assert token

    response = client.post(
        "/api/v1/auth/change-username",
        json={"current_password": "Operation123!", "username": "admin"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "AUTH_USERNAME_EXISTS"


def test_sensitive_password_checks_share_internal_lock_state(api_client) -> None:
    client, factory = api_client
    login = _login(client, "operation", "Operation123!")
    assert login.status_code == 200, login.text

    for _ in range(4):
        response = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "WrongPass123!", "new_password": "Operation456!"},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "AUTH_CURRENT_PASSWORD_INVALID"

    locked = client.post(
        "/api/v1/auth/change-username",
        json={"current_password": "WrongPass123!", "username": "operation-locked"},
    )
    assert locked.status_code == 429
    assert locked.json()["code"] == "AUTH_SENSITIVE_ACTION_LOCKED"

    relogin = _login(client, "operation", "Operation123!")
    assert _failure_contract(relogin) == (401, "AUTH_LOGIN_FAILED", "用户名或密码错误")

    with factory() as db:
        user = db.scalar(select(User).where(User.username == "operation"))
        assert user is not None
        state = db.get(AuthLoginState, user.id)
        assert state is not None
        assert state.failed_count == 5
        assert state.locked_until is not None
        actions = db.scalars(select(AuditLog.action).where(AuditLog.resource_id == user.id)).all()
        assert actions.count("AUTH_PASSWORD_CHANGE_FAILED") == 4
        assert "AUTH_USERNAME_CHANGE_FAILED" in actions


def test_unknown_username_keeps_generic_failure_contract(api_client) -> None:
    client, _ = api_client
    response = _login(client, "does-not-exist", "Arbitrary-Wrong-Password!")
    assert _failure_contract(response) == (401, "AUTH_LOGIN_FAILED", "用户名或密码错误")


def test_production_nginx_has_dedicated_login_rate_limit_and_trusted_real_ip() -> None:
    nginx = Path("infra/nginx/production.conf.template").read_text(encoding="utf-8")
    compose = Path("docker-compose.prod.yml").read_text(encoding="utf-8")
    proxy_env = "TRUSTED_PROXY_CIDR: ${TRUSTED_PROXY_CIDR:-127.0.0.1/32}"
    assert "set_real_ip_from ${TRUSTED_PROXY_CIDR};" in nginx
    assert "real_ip_header X-Forwarded-For;" in nginx
    assert "real_ip_recursive on;" in nginx
    assert "zone=auth_login_limit:10m rate=10r/m" in nginx
    assert "location = /api/v1/auth/login" in nginx
    assert "limit_req zone=auth_login_limit burst=5 nodelay;" in nginx
    assert "limit_req_status 429;" in nginx
    assert nginx.index("location = /api/v1/auth/login") < nginx.index("location /api/")
    assert compose.count(proxy_env) == 2, "API validator and Nginx must receive identical Compose interpolation"


def test_auth_login_state_migration_is_on_current_chain_and_registered_with_alembic() -> None:
    migration = Path("migrations/versions/0005_auth_login_hardening.py").read_text(encoding="utf-8")
    env = Path("migrations/env.py").read_text(encoding="utf-8")
    assert 'revision = "0005_auth_login_hardening"' in migration
    assert 'down_revision = "0004_v12_reward_snapshot"' in migration
    assert '"auth_login_state"' in migration
    assert '"locked_until"' in migration
    assert "auth_models" in env

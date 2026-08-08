from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from apps.api.src.core.auth_models import AuthLoginState
from apps.api.src.core.models import AuditLog, User
from apps.api.src.services.auth_service import InternalAuthError, authenticate_internal


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

    # A correct password must not bypass an active account lock, but the client
    # must not learn that this username exists or is locked.
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
        actions = db.scalars(
            select(AuditLog.action).where(AuditLog.resource_id == user.id)
        ).all()
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
        actions = db.scalars(
            select(AuditLog.action).where(AuditLog.resource_id == user.id)
        ).all()
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


def test_logout_invalidates_previous_bearer_token_via_session_version(api_client) -> None:
    client, _ = api_client
    login = _login(client, "owner", "Owner123!")
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


def test_unknown_username_keeps_generic_failure_contract(api_client) -> None:
    client, _ = api_client
    response = _login(client, "does-not-exist", "Arbitrary-Wrong-Password!")
    assert _failure_contract(response) == (401, "AUTH_LOGIN_FAILED", "用户名或密码错误")


def test_production_nginx_has_dedicated_login_rate_limit_and_trusted_real_ip() -> None:
    nginx = Path("infra/nginx/production.conf.template").read_text(encoding="utf-8")
    compose = Path("docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "set_real_ip_from ${TRUSTED_PROXY_CIDR};" in nginx
    assert "real_ip_header X-Forwarded-For;" in nginx
    assert "real_ip_recursive on;" in nginx
    assert "zone=auth_login_limit:10m rate=10r/m" in nginx
    assert "location = /api/v1/auth/login" in nginx
    assert "limit_req zone=auth_login_limit burst=5 nodelay;" in nginx
    assert "limit_req_status 429;" in nginx
    assert nginx.index("location = /api/v1/auth/login") < nginx.index("location /api/")
    assert "TRUSTED_PROXY_CIDR: ${TRUSTED_PROXY_CIDR:-127.0.0.1/32}" in compose


def test_auth_login_state_migration_is_on_current_chain_and_registered_with_alembic() -> None:
    migration = Path("migrations/versions/0005_auth_login_hardening.py").read_text(encoding="utf-8")
    env = Path("migrations/env.py").read_text(encoding="utf-8")
    assert 'revision = "0005_auth_login_hardening"' in migration
    assert 'down_revision = "0004_v12_reward_snapshot"' in migration
    assert '"auth_login_state"' in migration
    assert '"locked_until"' in migration
    assert "auth_models" in env

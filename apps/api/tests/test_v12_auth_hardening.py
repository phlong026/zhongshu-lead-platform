from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from apps.api.src.core.auth_models import AuthLoginState
from apps.api.src.core.models import AuditLog, User


def _login(client, username: str, password: str):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"user-agent": "hardening-test/1.0", "x-real-ip": "203.0.113.10"},
    )


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


def test_internal_login_failures_persist_lock_and_expire_with_audit(api_client) -> None:
    client, factory = api_client
    wrong_password = "Definitely-Wrong-Password!"

    for _ in range(4):
        response = _login(client, "admin", wrong_password)
        assert response.status_code == 401
        assert response.json()["code"] == "AUTH_LOGIN_FAILED"

    locked = _login(client, "admin", wrong_password)
    assert locked.status_code == 429
    assert locked.json()["code"] == "AUTH_LOGIN_THROTTLED"

    # A correct password must not bypass an active account lock.
    blocked_correct = _login(client, "admin", "Admin123!")
    assert blocked_correct.status_code == 429
    assert blocked_correct.json()["code"] == "AUTH_LOGIN_THROTTLED"

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

        logs = db.scalars(
            select(AuditLog).where(AuditLog.resource_id == user.id)
        ).all()
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


def test_disabled_user_invalidates_existing_cookie_and_cannot_relogin(api_client) -> None:
    client, factory = api_client
    login = _login(client, "operation", "Operation123!")
    assert login.status_code == 200
    token = login.cookies.get("access_token")
    assert token

    with factory() as db:
        user = db.scalar(select(User).where(User.username == "operation"))
        assert user is not None
        user.status = "DISABLED"
        db.commit()

    client.cookies.set("access_token", token)
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 401
    assert me.json()["code"] == "AUTH_INVALID"

    relogin = _login(client, "operation", "Operation123!")
    assert relogin.status_code == 403
    assert relogin.json()["code"] == "AUTH_ACCOUNT_DISABLED"


def test_unknown_username_keeps_generic_failure_contract(api_client) -> None:
    client, _ = api_client
    response = _login(client, "does-not-exist", "Arbitrary-Wrong-Password!")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_LOGIN_FAILED"
    assert response.json()["message"] == "用户名或密码错误"


def test_production_nginx_has_dedicated_login_rate_limit() -> None:
    nginx = Path("infra/nginx/production.conf.template").read_text(encoding="utf-8")
    assert "zone=auth_login_limit:10m rate=10r/m" in nginx
    assert "location = /api/v1/auth/login" in nginx
    assert "limit_req zone=auth_login_limit burst=5 nodelay;" in nginx
    assert "limit_req_status 429;" in nginx
    assert nginx.index("location = /api/v1/auth/login") < nginx.index("location /api/")


def test_auth_login_state_migration_is_on_current_chain() -> None:
    migration = Path("migrations/versions/0005_auth_login_hardening.py").read_text(encoding="utf-8")
    assert 'revision = "0005_auth_login_hardening"' in migration
    assert 'down_revision = "0004_v12_reward_snapshot"' in migration
    assert '"auth_login_state"' in migration
    assert '"locked_until"' in migration

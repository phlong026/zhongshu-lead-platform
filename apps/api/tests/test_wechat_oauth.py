from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from jwt import InvalidTokenError
from sqlalchemy import select

from apps.api.src.core.errors import AppError
from apps.api.src.core.models import AuditLog, Company, InviteToken, User, UserRole, WechatIdentity
from apps.api.src.core.security import create_signed_state, decode_signed_state
from apps.api.src.integrations.wechat import WechatOAuthClient, WechatOAuthIdentity
from apps.api.src.routers.auth import _WECHAT_CHANNEL_FAILURE_CODES
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.auth_service import create_company_invite, login_or_bind_wechat
from apps.api.src.services.company_service import create_company
from apps.api.src.services.rbac import assign_role


def _company(db):
    company = create_company(
        db,
        CompanyCreateBody(
            code="WX001",
            name="微信OAuth测试加盟商",
            owner_name="张老板",
            region_codes=["310100"],
            capabilities=[{"category_code": "OLD_RENOVATION", "brand_code": None}],
        ),
    )
    db.flush()
    return company


def _state_from_authorization_url(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


def test_signed_oauth_state_round_trip():
    token = create_signed_state({"invite": "abc", "return_url": "/h5/#/home"}, purpose="wechat-oauth")
    data = decode_signed_state(token, purpose="wechat-oauth")
    assert data["invite"] == "abc"
    assert data["return_url"] == "/h5/#/home"
    with pytest.raises(InvalidTokenError):
        decode_signed_state(token, purpose="other")


def test_wechat_authorization_url(monkeypatch):
    import apps.api.src.integrations.wechat as module

    monkeypatch.setattr(module.settings, "wechat_app_id", "wx-demo")
    monkeypatch.setattr(module.settings, "wechat_oauth_redirect_uri", "https://example.com/api/v1/auth/wechat/callback")
    monkeypatch.setattr(module.settings, "wechat_oauth_scope", "snsapi_base")
    url = WechatOAuthClient().authorization_url(state="signed-state")
    assert "appid=wx-demo" in url
    assert "scope=snsapi_base" in url
    assert "state=signed-state" in url
    assert url.endswith("#wechat_redirect")


def test_first_login_binds_company_and_repeat_login_needs_no_invite(db):
    company = _company(db)
    _, raw, _ = create_company_invite(db, company.id, None, 24)
    user, _ = login_or_bind_wechat(
        db,
        openid="wx-openid-001",
        unionid="union-001",
        nickname="张老板",
        invite_token=raw,
    )
    db.commit()
    assert user.company_id == company.id
    identity = db.scalar(select(WechatIdentity).where(WechatIdentity.openid == "wx-openid-001"))
    assert identity and identity.unionid == "union-001"

    repeated, _ = login_or_bind_wechat(
        db,
        openid="wx-openid-001",
        unionid="union-001",
        nickname="张老板新昵称",
    )
    db.commit()
    assert repeated.id == user.id
    assert identity.nickname == "张老板新昵称"


def test_unbound_wechat_without_invite_is_rejected(db):
    with pytest.raises(AppError) as exc:
        login_or_bind_wechat(db, openid="unbound")
    assert exc.value.code == "AUTH_WECHAT_NOT_BOUND"


def test_bind_intent_purpose_is_isolated_from_legacy_oauth_state():
    legacy = create_signed_state({"invite": "raw-legacy-token", "return_url": "/h5/#/home"}, purpose="wechat-oauth")
    with pytest.raises(InvalidTokenError):
        decode_signed_state(legacy, purpose="wechat-oauth-bind")
    bind = create_signed_state(
        {"invite_id": "i-1", "company_id": "c-1", "binding_confirmed": True, "return_url": "/h5/#/home"},
        purpose="wechat-oauth-bind",
    )
    with pytest.raises(InvalidTokenError):
        decode_signed_state(bind, purpose="wechat-oauth")


def test_confirm_start_issues_short_lived_binding_intent(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        company = _company(db)
        invite, raw, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
        invite_id, company_id = invite.id, company.id
    response = client.post(
        "/api/v1/auth/invites/confirm-start",
        json={"invite": raw, "return_url": "/h5/#/home"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    state = _state_from_authorization_url(data["authorization_url"])
    payload = decode_signed_state(state, purpose="wechat-oauth-bind")
    assert payload["invite_id"] == invite_id
    assert payload["company_id"] == company_id
    assert payload["binding_confirmed"] is True
    assert payload["return_url"] == "/h5/#/home"
    # signed state 不携带 raw invite token
    assert raw not in state and raw not in data["authorization_url"]
    expires_at = datetime.fromisoformat(data["expires_at"])
    now = datetime.now(timezone.utc)
    assert now < expires_at <= now + timedelta(minutes=11)

    # 恶意 return_url 被收敛为站内路径
    hostile = client.post(
        "/api/v1/auth/invites/confirm-start",
        json={"invite": raw, "return_url": "https://evil.example/steal"},
    )
    assert hostile.status_code == 200
    hostile_payload = decode_signed_state(
        _state_from_authorization_url(hostile.json()["data"]["authorization_url"]),
        purpose="wechat-oauth-bind",
    )
    assert hostile_payload["return_url"] == "/h5/#/home"

    # 反斜杠形式（浏览器会把 /\evil.com 解析为 //evil.com）同样必须收敛
    backslash = client.post(
        "/api/v1/auth/invites/confirm-start",
        json={"invite": raw, "return_url": "/\\evil.com"},
    )
    assert backslash.status_code == 200
    backslash_payload = decode_signed_state(
        _state_from_authorization_url(backslash.json()["data"]["authorization_url"]),
        purpose="wechat-oauth-bind",
    )
    assert backslash_payload["return_url"] == "/h5/#/home"


def test_confirm_start_rejects_invalid_invite(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/api/v1/auth/invites/confirm-start",
        json={"invite": "not-a-real-invite-token-000000", "return_url": "/h5/#/home"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "AUTH_INVITE_INVALID"


def test_confirm_start_rejects_an_existing_internal_session(api_client) -> None:
    client, factory = api_client
    logged_in = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin123!"},
    )
    assert logged_in.status_code == 200, logged_in.text
    with factory() as db:
        company = _company(db)
        invite, raw, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
        invite_id = invite.id

    response = client.post(
        "/api/v1/auth/invites/confirm-start",
        json={"invite": raw, "return_url": "/h5/v12-workbench.html"},
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "AUTH_BINDING_REQUIRES_CLEAN_SESSION"
    with factory() as db:
        invite = db.get(InviteToken, invite_id)
        assert invite is not None and invite.used_at is None


def test_binding_callback_rejects_an_existing_internal_session_before_wechat_exchange(
    api_client,
    monkeypatch,
) -> None:
    client, factory = api_client
    logged_in = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin123!"},
    )
    assert logged_in.status_code == 200, logged_in.text
    with factory() as db:
        company = _company(db)
        invite, _, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
        invite_id = invite.id
        company_id = company.id
    exchanged = False

    def _exchange(_self, _code):
        nonlocal exchanged
        exchanged = True
        return WechatOAuthIdentity(openid="must-not-bind", unionid=None, nickname="误绑用户")

    monkeypatch.setattr(WechatOAuthClient, "exchange_code", _exchange)
    state = create_signed_state(
        {
            "invite_id": invite_id,
            "company_id": company_id,
            "binding_confirmed": True,
            "return_url": "/h5/v12-workbench.html",
        },
        purpose="wechat-oauth-bind",
    )

    response = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "must-not-exchange", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    assert response.headers["location"] == (
        "/h5/auth-error.html?code=AUTH_BINDING_REQUIRES_CLEAN_SESSION"
    )
    assert exchanged is False
    assert "set-cookie" not in response.headers
    with factory() as db:
        invite = db.get(InviteToken, invite_id)
        company = db.get(Company, company_id)
        identity = db.scalar(
            select(WechatIdentity).where(WechatIdentity.openid == "must-not-bind")
        )
        assert invite is not None and invite.used_at is None
        assert company is not None and company.primary_user_id is None
        assert identity is None


def test_mock_binding_callback_obeys_the_same_clean_session_boundary(api_client) -> None:
    client, factory = api_client
    logged_in = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin123!"},
    )
    assert logged_in.status_code == 200, logged_in.text
    with factory() as db:
        company = _company(db)
        invite, _, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
        invite_id = invite.id
        company_id = company.id
    state = create_signed_state(
        {
            "invite_id": invite_id,
            "company_id": company_id,
            "binding_confirmed": True,
            "return_url": "/h5/v12-workbench.html",
        },
        purpose="wechat-oauth-bind",
    )

    response = client.post(
        "/api/v1/auth/wechat/mock-callback",
        json={"state": state, "openid": "mock-must-not-bind", "nickname": "误绑用户"},
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "AUTH_BINDING_REQUIRES_CLEAN_SESSION"
    with factory() as db:
        invite = db.get(InviteToken, invite_id)
        identity = db.scalar(
            select(WechatIdentity).where(WechatIdentity.openid == "mock-must-not-bind")
        )
        assert invite is not None and invite.used_at is None
        assert identity is None


def test_bound_employee_cannot_consume_a_company_owner_invite(db) -> None:
    company = _company(db)
    invite, raw, _ = create_company_invite(db, company.id, None, 24)
    employee = User(
        display_name="加盟商员工",
        company_id=company.id,
        status="ACTIVE",
    )
    db.add(employee)
    db.flush()
    assign_role(db, employee, "FRANCHISE_EMPLOYEE")
    db.add(WechatIdentity(openid="employee-openid", user_id=employee.id))
    db.commit()

    with pytest.raises(AppError) as exc:
        login_or_bind_wechat(
            db,
            openid="employee-openid",
            invite_token=raw,
            expected_company_id=company.id,
        )

    assert exc.value.code == "AUTH_WECHAT_IDENTITY_CONFLICT"
    db.rollback()
    db.refresh(invite)
    db.refresh(company)
    assert invite.used_at is None
    assert company.primary_user_id is None


def test_oauth_callback_binds_new_wechat_only_with_confirmed_intent(api_client, monkeypatch) -> None:
    client, factory = api_client
    with factory() as db:
        company = _company(db)
        invite, raw, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
        company_id = company.id
    monkeypatch.setattr(
        WechatOAuthClient,
        "exchange_code",
        lambda self, code: WechatOAuthIdentity(openid=f"oauth-{code}", unionid=None, nickname="授权用户"),
    )

    def _confirm(invite_raw: str) -> str:
        confirm = client.post("/api/v1/auth/invites/confirm-start", json={"invite": invite_raw})
        assert confirm.status_code == 200, confirm.text
        return _state_from_authorization_url(confirm.json()["data"]["authorization_url"])

    state = _confirm(raw)
    bound = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "code-ok", "state": state},
        follow_redirects=False,
    )
    assert bound.status_code == 302, bound.text
    with factory() as db:
        identity = db.scalar(select(WechatIdentity).where(WechatIdentity.openid == "oauth-code-ok"))
        assert identity is not None
        assert identity.user.company_id == company_id

    # legacy purpose 的 state 不允许首次绑定：新 openid 走旧式 state 直接失败
    legacy_state = create_signed_state({"invite": raw, "return_url": "/h5/#/home"}, purpose="wechat-oauth")
    rejected = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "code-legacy", "state": legacy_state},
        follow_redirects=False,
    )
    # P1-04：绑定类失败在浏览器上下文统一 302 到 H5 状态页，不再返回裸 JSON。
    assert rejected.status_code == 302
    assert "/h5/auth-error.html?code=AUTH_WECHAT_NOT_BOUND" in rejected.headers["location"]

    # 伪造的 bind purpose（缺少 binding_confirmed）同样拒绝
    forged = create_signed_state(
        {"invite_id": invite.id, "company_id": company_id, "return_url": "/h5/#/home"},
        purpose="wechat-oauth-bind",
    )
    unconfirmed = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "code-forged", "state": forged},
        follow_redirects=False,
    )
    assert unconfirmed.status_code == 302
    assert "/h5/auth-error.html?code=AUTH_BINDING_CONFIRM_REQUIRED" in unconfirmed.headers["location"]


def test_wechat_start_rejects_legacy_invite_entry_and_keeps_plain_login(api_client) -> None:
    """Phase 3.5/H2：旧 /wechat/start?invite= 入口显式拒绝，普通登录不受影响。"""

    client, _ = api_client
    legacy = client.get(
        "/api/v1/auth/wechat/start",
        params={"invite": "legacy-invite-token-abcdefghijklmnop"},
        follow_redirects=False,
    )
    assert legacy.status_code == 400
    assert legacy.json()["code"] == "AUTH_INVITE_ENTRY_DEPRECATED"

    plain = client.get(
        "/api/v1/auth/wechat/start",
        params={"return_url": "/h5/#/home"},
        follow_redirects=False,
    )
    assert plain.status_code == 302, plain.text
    location = plain.headers["location"]
    assert "open.weixin.qq.com" in location
    payload = decode_signed_state(_state_from_authorization_url(location), purpose="wechat-oauth")
    # legacy purpose 状态不再携带任何邀请信息，首次绑定只能走 confirm-start
    assert "invite" not in payload
    assert payload["return_url"] == "/h5/#/home"



def test_oauth_callback_redirects_binding_errors_to_h5_status_page(api_client) -> None:
    """P1-04：callback 的绑定类错误 302 到 H5 状态页，浏览器不再看到裸 JSON。"""

    client, _ = api_client
    invalid_state = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "code-x", "state": "garbage-state"},
        follow_redirects=False,
    )
    assert invalid_state.status_code == 302, invalid_state.text
    assert invalid_state.headers["location"] == "/h5/auth-error.html?code=AUTH_OAUTH_STATE_INVALID"

    forged = create_signed_state(
        {"invite_id": "i-x", "company_id": "c-x", "return_url": "/h5/#/home"},
        purpose="wechat-oauth-bind",
    )
    unconfirmed = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "code-y", "state": forged},
        follow_redirects=False,
    )
    assert unconfirmed.status_code == 302
    assert unconfirmed.headers["location"] == "/h5/auth-error.html?code=AUTH_BINDING_CONFIRM_REQUIRED"

def test_confirm_start_neutralizes_control_char_return_urls(api_client) -> None:
    """C1 整改：WHATWG URL 解析前会剥离 tab/LF/CR，"/\t/evil.com" 在浏览器等价
    于 "//evil.com"（跨域）。控制字符、反斜杠与非 /h5/ 前缀必须一律收敛。"""

    client, factory = api_client
    with factory() as db:
        company = _company(db)
        db.commit()
        _, raw_invite, _ = create_company_invite(db, company.id, None, 24)
        db.commit()

    hostile_values = [
        "/\t/evil.com",
        "/\t//evil.com",
        "/\n//evil.com",
        "/\r/evil.com",
        "/h5/#/home\x00",
        "/h5/#/home\x7f",
        "/\\evil.com",
        "/h5/#/ho\\me",
        "/admin/console",
        "/api/v1/auth/login",
    ]
    for value in hostile_values:
        response = client.post(
            "/api/v1/auth/invites/confirm-start",
            json={"invite": raw_invite, "return_url": value},
        )
        assert response.status_code == 200, response.text
        payload = decode_signed_state(
            _state_from_authorization_url(response.json()["data"]["authorization_url"]),
            purpose="wechat-oauth-bind",
        )
        assert payload["return_url"] == "/h5/#/home", f"未收敛: {value!r}"


def test_wechat_start_neutralizes_control_char_return_urls(api_client) -> None:
    """C1 整改同样覆盖 /wechat/start 的 return_url 注入面（可外链投递的 GET）。"""

    client, _factory = api_client
    for value in ["/\t/evil.com", "/\n//evil.com", "/admin/console", "//evil.example/steal"]:
        response = client.get(
            "/api/v1/auth/wechat/start",
            params={"return_url": value},
            follow_redirects=False,
        )
        assert response.status_code == 302, response.text
        state = _state_from_authorization_url(response.headers["location"])
        payload = decode_signed_state(state, purpose="wechat-oauth")
        assert payload["return_url"] == "/h5/#/home", f"未收敛: {value!r}"


def test_confirm_start_keeps_legitimate_h5_return_url(api_client) -> None:
    """白名单不得误伤合法的 /h5/ 站内回跳目标。"""

    client, factory = api_client
    with factory() as db:
        company = _company(db)
        db.commit()
        _, raw_invite, _ = create_company_invite(db, company.id, None, 24)
        db.commit()

    response = client.post(
        "/api/v1/auth/invites/confirm-start",
        json={"invite": raw_invite, "return_url": "/h5/#/home"},
    )
    assert response.status_code == 200, response.text
    payload = decode_signed_state(
        _state_from_authorization_url(response.json()["data"]["authorization_url"]),
        purpose="wechat-oauth-bind",
    )
    assert payload["return_url"] == "/h5/#/home"


def test_confirm_start_rejects_a_different_role_workbench_return_url(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        company = _company(db)
        db.commit()
        _, raw_invite, _ = create_company_invite(db, company.id, None, 24)
        db.commit()

    for requested in ("/h5/call/index.html", "/h5/admin/", "/h5/unknown.html"):
        response = client.post(
            "/api/v1/auth/invites/confirm-start",
            json={"invite": raw_invite, "return_url": requested},
        )
        assert response.status_code == 200, response.text
        payload = decode_signed_state(
            _state_from_authorization_url(response.json()["data"]["authorization_url"]),
            purpose="wechat-oauth-bind",
        )
        assert payload["return_url"] == "/h5/#/home"

def test_bound_user_can_relogin_without_invite_via_legacy_start(api_client, monkeypatch) -> None:
    """C2 整改守护：已绑定负责人无邀请也能从 H5 普通登录，且未绑定新微信被引导
    到状态页（而不是前端拒绝服务）。后端 legacy 路径必须保持可用。"""

    client, factory = api_client
    with factory() as db:
        company = _company(db)
        invite, raw, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
        company_id = company.id
    monkeypatch.setattr(
        WechatOAuthClient,
        "exchange_code",
        lambda self, code: WechatOAuthIdentity(openid=f"oauth-{code}", unionid=None, nickname="授权用户"),
    )

    # 首次绑定：邀请确认 -> bind state -> callback 成功
    confirm = client.post(
        "/api/v1/auth/invites/confirm-start",
        json={"invite": raw, "return_url": "/h5/#/home"},
    )
    assert confirm.status_code == 200, confirm.text
    bind_state = _state_from_authorization_url(confirm.json()["data"]["authorization_url"])
    first = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "c2-bind", "state": bind_state},
        follow_redirects=False,
    )
    assert first.status_code == 302, first.text

    # C2 核心：无邀请 GET /wechat/start 走 legacy 登录，state 不携带 invite
    start = client.get("/api/v1/auth/wechat/start", follow_redirects=False)
    assert start.status_code == 302, start.text
    legacy_state = _state_from_authorization_url(start.headers["location"])
    payload = decode_signed_state(legacy_state, purpose="wechat-oauth")
    assert "invite" not in payload and "invite_id" not in payload
    assert payload["return_url"] == "/h5/#/home"

    # 已绑定身份经 legacy state 重登成功：302 回 return_url 并下发 access_token cookie
    relogin = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "c2-bind", "state": legacy_state},
        follow_redirects=False,
    )
    assert relogin.status_code == 302, relogin.text
    assert relogin.headers["location"] == "/h5/#/home"
    assert "access_token" in relogin.headers["set-cookie"]

    # 重登不新建绑定，也不改动公司归属
    with factory() as db:
        identities = db.scalars(
            select(WechatIdentity).where(WechatIdentity.openid == "oauth-c2-bind")
        ).all()
        assert len(identities) == 1
        assert identities[0].user.company_id == company_id

    # 未绑定的新微信走无邀请入口：引导到状态页，而非拒绝服务
    fresh_start = client.get("/api/v1/auth/wechat/start", follow_redirects=False)
    fresh_state = _state_from_authorization_url(fresh_start.headers["location"])
    fresh = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "c2-fresh", "state": fresh_state},
        follow_redirects=False,
    )
    assert fresh.status_code == 302, fresh.text
    assert "/h5/auth-error.html?code=AUTH_WECHAT_NOT_BOUND" in fresh.headers["location"]

def test_binding_after_company_disable_lands_on_status_page(api_client, monkeypatch) -> None:
    """I7 守护：确认在先、停用在后的时序下，callback 首次绑定必须以
    AUTH_COMPANY_DISABLED 落状态页，且不创建身份、不占用主账号。"""

    client, factory = api_client
    with factory() as db:
        company = _company(db)
        invite, raw, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
        company_id = company.id
    confirm = client.post(
        "/api/v1/auth/invites/confirm-start",
        json={"invite": raw, "return_url": "/h5/#/home"},
    )
    assert confirm.status_code == 200, confirm.text
    bind_state = _state_from_authorization_url(confirm.json()["data"]["authorization_url"])

    monkeypatch.setattr(
        WechatOAuthClient,
        "exchange_code",
        lambda self, code: WechatOAuthIdentity(openid=f"oauth-{code}", unionid=None, nickname="授权用户"),
    )
    with factory() as db:
        company_row = db.get(Company, company_id)
        assert company_row is not None
        company_row.status = "DISABLED"
        db.commit()

    response = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "i7-code", "state": bind_state},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    assert "/h5/auth-error.html?code=AUTH_COMPANY_DISABLED" in response.headers["location"]
    with factory() as db:
        identities = db.scalars(
            select(WechatIdentity).where(WechatIdentity.openid == "oauth-i7-code")
        ).all()
        assert identities == []
        company_row = db.get(Company, company_id)
        assert company_row is not None and company_row.primary_user_id is None

def test_callback_audit_distinguishes_bind_from_relogin(api_client, monkeypatch) -> None:
    """I4：绑定意图完成记 WECHAT_BIND（含 invite_id 追溯），legacy 重登
    记 WECHAT_OAUTH_LOGIN；两类审计行都带 IP 与 UA。"""

    client, factory = api_client
    with factory() as db:
        company = _company(db)
        invite, raw, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
        invite_id = invite.id
    monkeypatch.setattr(
        WechatOAuthClient,
        "exchange_code",
        lambda self, code: WechatOAuthIdentity(openid=f"oauth-{code}", unionid=None, nickname="授权用户"),
    )
    confirm = client.post(
        "/api/v1/auth/invites/confirm-start",
        json={"invite": raw, "return_url": "/h5/#/home"},
        headers={"user-agent": "i4-audit-h5"},
    )
    assert confirm.status_code == 200, confirm.text
    bind_state = _state_from_authorization_url(confirm.json()["data"]["authorization_url"])
    bound = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "i4-bind", "state": bind_state},
        follow_redirects=False,
        headers={"user-agent": "i4-audit-h5"},
    )
    assert bound.status_code == 302, bound.text

    start = client.get("/api/v1/auth/wechat/start", follow_redirects=False)
    legacy_state = _state_from_authorization_url(start.headers["location"])
    relogin = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "i4-bind", "state": legacy_state},
        follow_redirects=False,
        headers={"user-agent": "i4-audit-h5"},
    )
    assert relogin.status_code == 302, relogin.text

    with factory() as db:
        bind_log = db.scalar(select(AuditLog).where(AuditLog.action == "WECHAT_BIND"))
        assert bind_log is not None
        assert bind_log.metadata_json.get("invite_id") == invite_id
        assert bind_log.user_agent == "i4-audit-h5"
        login_log = db.scalar(
            select(AuditLog).where(AuditLog.action == "WECHAT_OAUTH_LOGIN")
        )
        assert login_log is not None
        assert login_log.user_agent == "i4-audit-h5"


def test_callback_failure_writes_audit_and_discards_partial_writes(api_client, monkeypatch) -> None:
    """P2-5：callback 失败不再零审计——WECHAT_OAUTH_CALLBACK_FAILED 落
    reason_code/display_code/flow/failure_class 与 invite_id/company_id 追溯
    关联；且落审计前先 rollback，占用主账号失败途中创建的 user/identity/
    邀请消费不得随审计提交一起漏进库里（codex #5：孤儿 User/UserRole 与
    成功审计也必须锁住）。"""

    client, factory = api_client
    with factory() as db:
        company = _company(db)
        invite, raw, _ = create_company_invite(db, company.id, None, 24)
        invite_id = invite.id
        company_id = company.id
        # 基线计数：seed_demo 会给内部账号授予角色，以「前后计数不变」锁定
        # 失败路径不新增任何角色授予。
        baseline_roles = len(db.scalars(select(UserRole)).all())
        # 直接占用主账号（模型为裸字符串无外键），制造「邀请有效但公司已绑定」：
        # 失败发生在 add(user)/add(identity) 之后，正是 rollback 的守护点。
        company.primary_user_id = "u-probe-taken-primary"
        db.commit()
    monkeypatch.setattr(
        WechatOAuthClient,
        "exchange_code",
        lambda self, code: WechatOAuthIdentity(openid=f"p25-{code}", unionid=None, nickname="失败用户"),
    )
    confirm = client.post(
        "/api/v1/auth/invites/confirm-start",
        json={"invite": raw, "return_url": "/h5/#/home"},
        headers={"user-agent": "p25-audit-h5"},
    )
    assert confirm.status_code == 200, confirm.text
    bind_state = _state_from_authorization_url(confirm.json()["data"]["authorization_url"])

    failed = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "p25-fail", "state": bind_state},
        follow_redirects=False,
        headers={"user-agent": "p25-audit-h5"},
    )
    assert failed.status_code == 302, failed.text
    assert failed.headers["location"] == "/h5/auth-error.html?code=AUTH_COMPANY_ALREADY_BOUND"

    # codex #6：state 未通过验签的失败同样必须有审计，且 flow=unknown。
    invalid = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "p25-fail", "state": "garbage-state"},
        follow_redirects=False,
        headers={"user-agent": "p25-audit-h5"},
    )
    assert invalid.status_code == 302
    assert invalid.headers["location"] == "/h5/auth-error.html?code=AUTH_OAUTH_STATE_INVALID"

    with factory() as db:
        bind_failed_rows = db.scalars(
            select(AuditLog).where(AuditLog.action == "WECHAT_OAUTH_CALLBACK_FAILED")
        ).all()
        assert len(bind_failed_rows) == 2, "两类失败路径都必须留下审计行"
        by_reason = {row.metadata_json.get("reason_code"): row for row in bind_failed_rows}
        already_bound = by_reason["AUTH_COMPANY_ALREADY_BOUND"]
        metadata = already_bound.metadata_json
        assert metadata.get("display_code") == "AUTH_COMPANY_ALREADY_BOUND"
        assert metadata.get("status_code") == 409
        assert metadata.get("flow") == "bind"
        assert metadata.get("failure_class") == "business"
        assert already_bound.resource_id == invite_id, "失败审计须关联邀请"
        assert already_bound.company_id == company_id, "失败审计须关联公司"
        assert already_bound.user_agent == "p25-audit-h5"

        state_invalid = by_reason["AUTH_OAUTH_STATE_INVALID"]
        assert state_invalid.metadata_json.get("flow") == "unknown"
        assert state_invalid.metadata_json.get("failure_class") == "security"
        assert state_invalid.resource_id is None

        # rollback 守护：半途写入不得入库。
        leaked_identity = db.scalar(
            select(WechatIdentity).where(WechatIdentity.openid == "p25-p25-fail")
        )
        assert leaked_identity is None, "失败的绑定不得残留微信身份"
        leaked_users = db.scalars(select(User).where(User.company_id == company_id)).all()
        assert leaked_users == [], "失败的绑定不得残留孤儿用户"
        all_roles = db.scalars(select(UserRole)).all()
        assert len(all_roles) == baseline_roles, "失败的绑定不得残留角色授予"
        invite_after = db.get(InviteToken, invite_id)
        assert invite_after.used_at is None, "失败的绑定不得消费邀请"
        assert invite_after.revoked_at is None
        success_logs = db.scalars(
            select(AuditLog).where(AuditLog.action.in_(["WECHAT_BIND", "WECHAT_OAUTH_LOGIN"]))
        ).all()
        assert success_logs == [], "失败路径不得产生成功审计"


def test_callback_failure_audit_persistence_failure_keeps_302(api_client, monkeypatch) -> None:
    """P2-5/codex #1、#7：审计持久化自身失败（含 rollback 抛错）不得反噬
    302 契约——兜底走结构化日志，H5 仍收到状态页重定向。"""

    client, factory = api_client

    def _broken_audit(*args, **kwargs):
        raise RuntimeError("audit storage down")

    monkeypatch.setattr("apps.api.src.routers.auth.write_audit", _broken_audit)
    response = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "p25-audit-down", "state": "garbage-state"},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/h5/auth-error.html?code=AUTH_OAUTH_STATE_INVALID"

    with factory() as db:
        rows = db.scalars(
            select(AuditLog).where(AuditLog.action == "WECHAT_OAUTH_CALLBACK_FAILED")
        ).all()
        assert rows == [], "审计写入失败时不得留下半截审计行"


def test_confirm_start_state_ttl_is_tightened(api_client) -> None:
    """I12：绑定预授权 state 的 TTL 显式为 5 分钟常量，不随通用默认漂移。"""

    client, factory = api_client
    with factory() as db:
        company = _company(db)
        _, raw, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
    confirm = client.post(
        "/api/v1/auth/invites/confirm-start",
        json={"invite": raw, "return_url": "/h5/#/home"},
    )
    assert confirm.status_code == 200, confirm.text
    payload = decode_signed_state(
        _state_from_authorization_url(confirm.json()["data"]["authorization_url"]),
        purpose="wechat-oauth-bind",
    )
    assert int(payload["exp"]) - int(payload["iat"]) == 5 * 60


def test_expired_bind_intent_state_is_rejected_at_callback(api_client, monkeypatch) -> None:
    """I17：过期的绑定意图 state 在 callback 按状态页语义拒绝，不得回退裸 JSON 或落库。"""

    client, factory = api_client
    with factory() as db:
        company = _company(db)
        _, raw, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
    confirm = client.post(
        "/api/v1/auth/invites/confirm-start",
        json={"invite": raw, "return_url": "/h5/#/home"},
    )
    assert confirm.status_code == 200, confirm.text
    payload = decode_signed_state(
        _state_from_authorization_url(confirm.json()["data"]["authorization_url"]),
        purpose="wechat-oauth-bind",
    )

    # 同样的意图字段，但用已过期的签名（exp 在过去）：签名合法，仅时间窗失效。
    expired_state = create_signed_state(
        {
            "invite_id": payload["invite_id"],
            "company_id": payload["company_id"],
            "binding_confirmed": True,
            "return_url": "/h5/#/home",
        },
        purpose="wechat-oauth-bind",
        expires_minutes=-1,
    )
    monkeypatch.setattr(
        WechatOAuthClient,
        "exchange_code",
        lambda self, code: WechatOAuthIdentity(openid="i17-expired-openid", unionid=None, nickname="过期state用户"),
    )
    response = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "i17-code", "state": expired_state},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/h5/auth-error.html?code=AUTH_OAUTH_STATE_INVALID"

    with factory() as db:
        leaked = db.scalar(select(WechatIdentity).where(WechatIdentity.openid == "i17-expired-openid"))
        assert leaked is None, "过期 state 不得完成绑定或落库"



# N12：通道告警断言由码集合驱动——从 _WECHAT_CHANNEL_FAILURE_CODES 删码、
# 或把告警条件放宽为「任意 5xx」都会让对应参数用例变红，防告警静默漂移。
@pytest.mark.parametrize("code", sorted(_WECHAT_CHANNEL_FAILURE_CODES))
def test_callback_upstream_failure_keeps_specific_code_and_alerts(api_client, monkeypatch, caplog, code) -> None:
    """P2-1：微信通道故障码显式透传到 H5（不再折叠为 AUTH_FAILED），
    失败审计归 failure_class=upstream，服务端落 error 级结构化日志
    （codex #3：日志本身必须被断言，防告警被静默删除或降级）。
    N12：本用例走 /wechat/start（无 invite）→ flow=='login'，审计行的
    flow 字段与 login 分支一并锁定。"""

    import logging as _logging

    client, factory = api_client

    def _channel_down(self, code_param):
        raise AppError(code, f"通道故障（{code}）", 502)

    monkeypatch.setattr(WechatOAuthClient, "exchange_code", _channel_down)
    start = client.get("/api/v1/auth/wechat/start", follow_redirects=False)
    valid_state = _state_from_authorization_url(start.headers["location"])
    with caplog.at_level(_logging.ERROR, logger="zhongshu.auth"):
        response = client.get(
            "/api/v1/auth/wechat/callback",
            params={"code": "p21-down", "state": valid_state},
            follow_redirects=False,
        )
    assert response.status_code == 302, response.text
    assert (
        response.headers["location"] == f"/h5/auth-error.html?code={code}"
    ), "通道故障码必须显式透传，供 H5 给出稍后重试指引"

    channel_errors = [
        record for record in caplog.records if record.name == "zhongshu.auth" and record.levelno == _logging.ERROR
    ]
    assert channel_errors, "通道故障必须留下 error 级日志供健康度告警"
    assert channel_errors[0].reason_code == code
    assert channel_errors[0].flow == "login"
    assert channel_errors[0].status_code == 502

    with factory() as db:
        audit_row = db.scalar(
            select(AuditLog).where(AuditLog.action == "WECHAT_OAUTH_CALLBACK_FAILED")
        )
        assert audit_row is not None
        assert audit_row.metadata_json.get("reason_code") == code
        assert audit_row.metadata_json.get("failure_class") == "upstream"
        assert audit_row.metadata_json.get("flow") == "login"


def test_callback_wechat_failure_details_never_leak(api_client, monkeypatch, caplog) -> None:
    """P2-1/codex #4：携带 errcode/errmsg details 的 WECHAT_OAUTH_FAILED 是
    真实泄露面——URL、审计 metadata、日志三处都不得出现微信原始 details。"""

    import logging as _logging

    client, factory = api_client

    def _failed_with_details(self, code):
        raise AppError(
            "WECHAT_OAUTH_FAILED",
            "微信授权失败",
            502,
            {"errcode": 40029, "errmsg": "invalid code, hint: [secret-hint]"},
        )

    monkeypatch.setattr(WechatOAuthClient, "exchange_code", _failed_with_details)
    start = client.get("/api/v1/auth/wechat/start", follow_redirects=False)
    valid_state = _state_from_authorization_url(start.headers["location"])
    with caplog.at_level(_logging.ERROR, logger="zhongshu.auth"):
        response = client.get(
            "/api/v1/auth/wechat/callback",
            params={"code": "p21-raw", "state": valid_state},
            follow_redirects=False,
        )
    assert response.status_code == 302, response.text
    # 白名单码透传的是枚举本身；details（errcode/errmsg）不得拼进 URL。
    assert response.headers["location"] == "/h5/auth-error.html?code=WECHAT_OAUTH_FAILED"
    assert "40029" not in response.headers["location"]
    assert "secret-hint" not in response.headers["location"]

    dumped_logs = caplog.text
    assert "secret-hint" not in dumped_logs and "40029" not in dumped_logs, "日志不得携带微信原始 details"

    with factory() as db:
        audit_row = db.scalar(
            select(AuditLog).where(AuditLog.action == "WECHAT_OAUTH_CALLBACK_FAILED")
        )
        assert audit_row is not None
        audit_text = str(audit_row.metadata_json)
        assert "secret-hint" not in audit_text and "40029" not in audit_text, "审计不得携带微信原始 details"


def test_callback_unknown_error_code_collapses_to_auth_failed(api_client, monkeypatch) -> None:
    """P2-1/P3-2 回落负例：白名单外的任意异常码一律归并 AUTH_FAILED，
    异常细节（如微信 errcode/errmsg）不得拼进重定向 URL。"""

    client, _ = api_client

    def _weird(self, code):
        raise AppError("SOME_UNMAPPED_FAULT", "内部细节 message", 500, {"errcode": 40029})

    monkeypatch.setattr(WechatOAuthClient, "exchange_code", _weird)
    start = client.get("/api/v1/auth/wechat/start", follow_redirects=False)
    valid_state = _state_from_authorization_url(start.headers["location"])
    response = client.get(
        "/api/v1/auth/wechat/callback",
        params={"code": "p21-weird", "state": valid_state},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/h5/auth-error.html?code=AUTH_FAILED"
    assert "SOME_UNMAPPED_FAULT" not in response.headers["location"]
    assert "40029" not in response.headers["location"]


def test_callback_missing_params_redirect_to_status_page_not_bare_422(api_client) -> None:
    """P2-4：code/state 缺失属异常流量（微信正常回跳必带两者），但契约仍是
    302 状态页——必填 query 参数会被 FastAPI 在函数体之前 422 拒成裸 JSON，
    微信浏览器看到的是错误对象而非可读页面；改为可选默认空后在 try 内
    显式拒绝，走与 AppError 同款失败审计。"""

    client, factory = api_client

    # 无 state（也无 code）：state 前置校验直接拒绝
    response = client.get("/api/v1/auth/wechat/callback", follow_redirects=False)
    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/h5/auth-error.html?code=AUTH_OAUTH_STATE_INVALID"

    # 只缺 code：取有效 login state 后再打 callback
    start = client.get("/api/v1/auth/wechat/start", follow_redirects=False)
    valid_state = _state_from_authorization_url(start.headers["location"])
    response = client.get(
        "/api/v1/auth/wechat/callback",
        params={"state": valid_state},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/h5/auth-error.html?code=AUTH_FAILED"

    # 两次缺参失败都发生在意图解析前（flow=unknown），审计不得缺席
    with factory() as db:
        rows = db.scalars(
            select(AuditLog).where(AuditLog.action == "WECHAT_OAUTH_CALLBACK_FAILED")
        ).all()
        assert len(rows) == 2
        assert {row.metadata_json.get("reason_code") for row in rows} == {
            "AUTH_OAUTH_STATE_INVALID",
            "AUTH_FAILED",
        }
        assert all(row.metadata_json.get("flow") == "unknown" for row in rows)


def test_conflict_replay_relogs_bound_identity_without_reconsuming_invite(db):
    """I14：唯一约束冲突后的幂等重放——按已绑定路径登录同一账号，
    不重复消费邀请、不新建用户/身份。"""

    from apps.api.src.services.auth_service import _replay_after_conflict

    company = _company(db)
    _, raw, _ = create_company_invite(db, company.id, None, 24)
    bound, _ = login_or_bind_wechat(
        db,
        openid="wx-conflict-openid",
        unionid="u-1",
        nickname="并发胜者",
        invite_token=raw,
    )
    db.commit()
    invite = db.scalar(select(InviteToken).where(InviteToken.company_id == company.id))
    used_at = invite.used_at
    assert used_at is not None

    replayed, _ = _replay_after_conflict(
        db,
        openid="wx-conflict-openid",
        unionid="u-1",
        nickname="重放昵称",
        expected_company_id=company.id,
    )
    assert replayed.id == bound.id
    db.commit()

    invite = db.scalar(select(InviteToken).where(InviteToken.company_id == company.id))
    assert invite.used_at == used_at, "重放不得二次消费邀请"
    user_count = len(db.scalars(select(User).where(User.company_id == company.id)).all())
    assert user_count == 1, "重放不得新建用户"
    identity = db.scalar(select(WechatIdentity).where(WechatIdentity.openid == "wx-conflict-openid"))
    assert identity is not None
    assert identity.user_id == bound.id
    assert identity.nickname == "重放昵称"


def test_conflict_replay_rejects_ghost_identity_and_cross_company(db):
    """I14 重放的拒绝分支：并发方回滚导致身份消失按通用失败拒绝（500，
    不泄漏唯一约束细节）；expected_company_id 与既有绑定不符时保持与
    转发误绑同款的 409 拒绝语义。"""

    from apps.api.src.services.auth_service import _replay_after_conflict

    with pytest.raises(AppError) as ghost:
        _replay_after_conflict(db, openid="wx-ghost-openid", unionid=None, nickname=None, expected_company_id=None)
    assert ghost.value.code == "AUTH_FAILED"
    assert ghost.value.status_code == 500

    company = _company(db)
    _, raw, _ = create_company_invite(db, company.id, None, 24)
    login_or_bind_wechat(db, openid="wx-cross-openid", unionid=None, nickname="跨公司", invite_token=raw)
    db.commit()
    other = Company(code="WX002", name="另一家加盟商", status="ACTIVE")
    db.add(other)
    db.flush()
    with pytest.raises(AppError) as cross:
        _replay_after_conflict(
            db, openid="wx-cross-openid", unionid=None, nickname=None, expected_company_id=other.id
        )
    assert cross.value.code == "AUTH_WECHAT_BOUND_OTHER_COMPANY"


def test_callback_integrity_conflict_and_unknown_failure_stay_302(api_client, monkeypatch, caplog) -> None:
    """P2-4/codex #2/#5：service 重放之外的 IntegrityError 与任意未知异常
    都不得穿透成全局处理器的裸 JSON——统一收敛 302 AUTH_FAILED + 失败审计；
    日志只记异常类名，SQL 绑定参数（openid 等）不得落日志。"""

    import logging as _logging

    from sqlalchemy.exc import IntegrityError as _IntegrityError

    client, factory = api_client
    monkeypatch.setattr(
        WechatOAuthClient,
        "exchange_code",
        lambda self, code: WechatOAuthIdentity(openid=f"oauth-{code}", unionid=None, nickname="授权用户"),
    )
    start = client.get("/api/v1/auth/wechat/start", follow_redirects=False)
    valid_state = _state_from_authorization_url(start.headers["location"])

    def _hit_callback() -> object:
        return client.get(
            "/api/v1/auth/wechat/callback",
            params={"code": "p24-conflict", "state": valid_state},
            follow_redirects=False,
        )

    # IntegrityError（含绑定参数的 message）：302 + 审计 + 类名日志，参数不落日志
    with caplog.at_level(_logging.ERROR, logger="zhongshu.auth"):
        monkeypatch.setattr(
            "apps.api.src.routers.auth.login_or_bind_wechat",
            lambda *a, **k: (_ for _ in ()).throw(
                _IntegrityError(
                    "INSERT INTO wechat_identities ...",
                    {"openid": "p24-secret-openid", "nickname": "秘密昵称"},
                    RuntimeError("duplicate key"),
                )
            ),
        )
        response = _hit_callback()
    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/h5/auth-error.html?code=AUTH_FAILED"
    conflict_errors = [r for r in caplog.records if r.name == "zhongshu.auth" and r.levelno == _logging.ERROR]
    assert conflict_errors, "完整性冲突必须留 error 日志"
    assert conflict_errors[0].exception_class == "IntegrityError"
    assert "p24-secret-openid" not in caplog.text and "秘密昵称" not in caplog.text

    # 未知异常：同样 302 + 审计，而非 500 裸 JSON
    monkeypatch.setattr(
        "apps.api.src.routers.auth.login_or_bind_wechat",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom-unexpected")),
    )
    response = _hit_callback()
    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/h5/auth-error.html?code=AUTH_FAILED"

    with factory() as db:
        rows = db.scalars(
            select(AuditLog).where(AuditLog.action == "WECHAT_OAUTH_CALLBACK_FAILED")
        ).all()
        assert len(rows) == 2
        assert all(row.metadata_json.get("reason_code") == "AUTH_FAILED" for row in rows)
        assert all(row.metadata_json.get("failure_class") == "upstream" for row in rows)
        assert all(row.metadata_json.get("flow") == "login" for row in rows)
        # 半途写入不残留
        assert db.scalar(select(WechatIdentity).where(WechatIdentity.openid == "oauth-p24-conflict")) is None


def test_callback_rejections_leave_warning_log(api_client, monkeypatch, caplog) -> None:
    """P2-4/codex #4：缺参/业务拒绝不能只有数据库审计——request_completed
    只见 302 不含原因，必须有 warning 级结构化日志（reason_code/flow）。"""

    import logging as _logging

    client, _ = api_client
    with caplog.at_level(_logging.WARNING, logger="zhongshu.auth"):
        response = client.get("/api/v1/auth/wechat/callback", follow_redirects=False)
    assert response.status_code == 302, response.text
    warnings = [
        r
        for r in caplog.records
        if r.name == "zhongshu.auth" and r.levelno == _logging.WARNING and "rejected" in r.getMessage()
    ]
    assert warnings, "缺参拒绝必须留 warning 日志"
    assert warnings[0].reason_code == "AUTH_OAUTH_STATE_INVALID"
    assert warnings[0].flow == "unknown"


def test_callback_failure_audit_is_throttled_per_ip_and_reason(api_client) -> None:
    """N11：callback 失败审计按 IP+reason 节流——循环打坏 callback 不能把
    审计表当垃圾场；首条审计必须落库，同键后续失败降级为日志留痕。"""

    client, factory = api_client

    # 同一客户端连打 5 次坏 state：state 验签失败，reason 恒定
    for _ in range(5):
        response = client.get(
            "/api/v1/auth/wechat/callback",
            params={"state": "garbage", "code": "x"},
            follow_redirects=False,
        )
        assert response.status_code == 302
    with factory() as db:
        rows = db.scalars(
            select(AuditLog).where(AuditLog.action == "WECHAT_OAUTH_CALLBACK_FAILED")
        ).all()
        assert len(rows) == 1, "同 IP+同 reason 的重复失败只落首条审计"

    # 不同 reason（有效 login state 但缺 code → AUTH_FAILED）是独立节流键
    start = client.get("/api/v1/auth/wechat/start", follow_redirects=False)
    valid_state = _state_from_authorization_url(start.headers["location"])
    response = client.get(
        "/api/v1/auth/wechat/callback",
        params={"state": valid_state},
        follow_redirects=False,
    )
    assert response.status_code == 302
    with factory() as db:
        rows = db.scalars(
            select(AuditLog).where(AuditLog.action == "WECHAT_OAUTH_CALLBACK_FAILED")
        ).all()
        assert len(rows) == 2
        assert {row.metadata_json.get("reason_code") for row in rows} == {
            "AUTH_OAUTH_STATE_INVALID",
            "AUTH_FAILED",
        }


def test_wechat_start_channel_failure_redirects_to_status_page(api_client, monkeypatch, caplog) -> None:
    """N6：/wechat/start 是浏览器直接导航——通道故障（未配置/scope 非法）
    不得回裸 JSON，必须 302 H5 状态页 + 失败审计 + 通道 error 告警。"""

    import logging as _logging

    import apps.api.src.integrations.wechat as wechat_module

    client, factory = api_client

    with caplog.at_level(_logging.ERROR, logger="zhongshu.auth"):
        # 场景1：app_id 未配置
        monkeypatch.setattr(wechat_module.settings, "wechat_app_id", "")
        response = client.get("/api/v1/auth/wechat/start", follow_redirects=False)
        assert response.status_code == 302, response.text
        assert response.headers["location"] == "/h5/auth-error.html?code=WECHAT_NOT_CONFIGURED"

        # 场景2：scope 配置非法
        monkeypatch.setattr(wechat_module.settings, "wechat_app_id", "wx-test-only")
        monkeypatch.setattr(wechat_module.settings, "wechat_oauth_scope", "snsapi_private")
        response = client.get("/api/v1/auth/wechat/start", follow_redirects=False)
        assert response.status_code == 302, response.text
        assert response.headers["location"] == "/h5/auth-error.html?code=WECHAT_SCOPE_INVALID"

    with factory() as db:
        rows = db.scalars(
            select(AuditLog).where(AuditLog.action == "WECHAT_OAUTH_START_FAILED")
        ).all()
        assert {row.metadata_json.get("reason_code") for row in rows} == {
            "WECHAT_NOT_CONFIGURED",
            "WECHAT_SCOPE_INVALID",
        }
    errors = [
        record
        for record in caplog.records
        if record.levelno == _logging.ERROR and "channel failure" in record.message
    ]
    assert len(errors) == 2, "两个通道故障都必须落 error 级告警"


def test_confirm_start_audit_follows_authorization_url_outcome(api_client, monkeypatch, caplog) -> None:
    """N6：INVITE_CONFIRM_START 只能在 authorization_url 成功后落——通道
    故障时不得留下「已开始」的成功审计，改记 INVITE_CONFIRM_START_FAILED
    并以 503 透传给前端状态页。"""

    import logging as _logging

    client, factory = api_client
    with factory() as db:
        company = _company(db)
        invite, raw, _ = create_company_invite(db, company.id, None, 24)
        db.commit()
        invite_id = invite.id

    def raise_not_configured(self, *, state, scope=None):
        raise AppError("WECHAT_NOT_CONFIGURED", "微信公众号尚未配置", 503)

    monkeypatch.setattr(WechatOAuthClient, "authorization_url", raise_not_configured)
    with caplog.at_level(_logging.ERROR, logger="zhongshu.auth"):
        response = client.post(
            "/api/v1/auth/invites/confirm-start",
            json={"invite": raw, "return_url": "/h5/#/home"},
        )
    assert response.status_code == 503, response.text
    assert response.json()["code"] == "WECHAT_NOT_CONFIGURED"

    with factory() as db:
        started = db.scalars(
            select(AuditLog).where(AuditLog.action == "INVITE_CONFIRM_START")
        ).all()
        assert not started, "通道故障不得留下成功开始的审计"
        failed = db.scalars(
            select(AuditLog).where(AuditLog.action == "INVITE_CONFIRM_START_FAILED")
        ).all()
        assert len(failed) == 1
        assert failed[0].metadata_json.get("reason_code") == "WECHAT_NOT_CONFIGURED"
        assert failed[0].resource_id == invite_id
    errors = [
        record
        for record in caplog.records
        if record.levelno == _logging.ERROR and "channel failure" in record.message
    ]
    assert errors, "confirm-start 通道故障必须落 error 级告警"

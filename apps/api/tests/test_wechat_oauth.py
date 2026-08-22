from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from jwt import InvalidTokenError
from sqlalchemy import select

from apps.api.src.core.errors import AppError
from apps.api.src.core.models import AuditLog, Company, WechatIdentity
from apps.api.src.core.security import create_signed_state, decode_signed_state
from apps.api.src.integrations.wechat import WechatOAuthClient, WechatOAuthIdentity
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.auth_service import create_company_invite, login_or_bind_wechat
from apps.api.src.services.company_service import create_company


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
    assert "/h5/#/auth-error?code=AUTH_WECHAT_NOT_BOUND" in rejected.headers["location"]

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
    assert "/h5/#/auth-error?code=AUTH_BINDING_CONFIRM_REQUIRED" in unconfirmed.headers["location"]


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
    assert invalid_state.headers["location"] == "/h5/#/auth-error?code=AUTH_OAUTH_STATE_INVALID"

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
    assert unconfirmed.headers["location"] == "/h5/#/auth-error?code=AUTH_BINDING_CONFIRM_REQUIRED"

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
    assert "/h5/#/auth-error?code=AUTH_WECHAT_NOT_BOUND" in fresh.headers["location"]

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
    assert "/h5/#/auth-error?code=AUTH_COMPANY_DISABLED" in response.headers["location"]
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


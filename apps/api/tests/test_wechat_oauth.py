from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from jwt import InvalidTokenError
from sqlalchemy import select

from apps.api.src.core.errors import AppError
from apps.api.src.core.models import WechatIdentity
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
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "AUTH_WECHAT_NOT_BOUND"

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
    assert unconfirmed.status_code == 400
    assert unconfirmed.json()["code"] == "AUTH_BINDING_CONFIRM_REQUIRED"


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

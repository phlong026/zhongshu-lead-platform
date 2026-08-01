from __future__ import annotations

import pytest
from jwt import InvalidTokenError
from sqlalchemy import select

from apps.api.src.core.errors import AppError
from apps.api.src.core.models import WechatIdentity
from apps.api.src.core.security import create_signed_state, decode_signed_state
from apps.api.src.integrations.wechat import WechatOAuthClient
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
    _, raw = create_company_invite(db, company.id, None, 24)
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

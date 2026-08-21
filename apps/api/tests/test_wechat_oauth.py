from __future__ import annotations

import pytest
from jwt import InvalidTokenError
from sqlalchemy import select

from apps.api.src.core.errors import AppError
from apps.api.src.core.models import WechatIdentity
from apps.api.src.core.security import create_signed_state, decode_signed_state
from apps.api.src.integrations.wechat import WechatOAuthClient
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.company_service import create_company
from apps.api.src.services.invite_binding_service import (
    bind_wechat_with_confirmation,
    create_company_invite,
    create_confirmation_intent,
    login_bound_wechat,
)


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


def test_signed_oauth_state_round_trip_without_invite_payload():
    token = create_signed_state({"return_url": "/h5/#/home"}, purpose="wechat-oauth")
    data = decode_signed_state(token, purpose="wechat-oauth")
    assert "invite" not in data
    assert data["return_url"] == "/h5/#/home"
    with pytest.raises(InvalidTokenError):
        decode_signed_state(token, purpose="invite-binding-confirmation")


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


def test_first_login_requires_confirmation_and_repeat_login_needs_no_invite(db):
    company = _company(db)
    created = create_company_invite(db, company.id, None, 24)
    started = create_confirmation_intent(db, created.raw_token, "/h5/#/home")
    user, _, _ = bind_wechat_with_confirmation(
        db,
        started.confirmation_intent,
        openid="wx-openid-001",
        unionid="union-001",
        nickname="张老板",
    )
    db.commit()
    assert user.company_id == company.id
    identity = db.scalar(select(WechatIdentity).where(WechatIdentity.openid == "wx-openid-001"))
    assert identity and identity.unionid == "union-001"

    repeated, _ = login_bound_wechat(
        db,
        openid="wx-openid-001",
        unionid="union-001",
        nickname="张老板新昵称",
    )
    db.commit()
    assert repeated.id == user.id
    db.refresh(identity)
    assert identity.nickname == "张老板新昵称"


def test_unbound_wechat_without_invite_is_rejected(db):
    with pytest.raises(AppError) as exc:
        login_bound_wechat(db, openid="unbound")
    assert exc.value.code == "AUTH_WECHAT_NOT_BOUND"

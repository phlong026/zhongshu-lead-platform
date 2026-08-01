from __future__ import annotations

import pytest
from jwt import InvalidTokenError

from apps.api.src.core.security import create_signed_state, decode_signed_state
from apps.api.src.integrations.wechat import WechatOAuthClient


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
    url = WechatOAuthClient().authorization_url(state="signed-state")
    assert "appid=wx-demo" in url
    assert "scope=snsapi_base" in url
    assert "state=signed-state" in url
    assert url.endswith("#wechat_redirect")

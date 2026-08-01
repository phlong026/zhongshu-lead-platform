from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.errors import AppError

settings = get_settings()


@dataclass(frozen=True)
class WechatSendResult:
    success: bool
    message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None




@dataclass(frozen=True)
class WechatOAuthIdentity:
    openid: str
    unionid: str | None = None
    nickname: str | None = None


class WechatOAuthClient:
    def authorization_url(self, *, state: str, scope: str = "snsapi_base") -> str:
        if not settings.wechat_app_id:
            raise AppError("WECHAT_NOT_CONFIGURED", "微信公众号尚未配置", 503)
        from urllib.parse import quote

        redirect_uri = quote(settings.wechat_oauth_redirect_uri, safe="")
        return (
            "https://open.weixin.qq.com/connect/oauth2/authorize"
            f"?appid={settings.wechat_app_id}&redirect_uri={redirect_uri}"
            f"&response_type=code&scope={scope}&state={state}#wechat_redirect"
        )

    def exchange_code(self, code: str) -> WechatOAuthIdentity:
        if not settings.wechat_app_id or not settings.wechat_app_secret:
            raise AppError("WECHAT_NOT_CONFIGURED", "微信公众号尚未配置", 503)
        response = httpx.get(
            "https://api.weixin.qq.com/sns/oauth2/access_token",
            params={
                "appid": settings.wechat_app_id,
                "secret": settings.wechat_app_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("openid"):
            raise AppError("WECHAT_OAUTH_FAILED", "微信授权失败", 502, {"errcode": data.get("errcode"), "errmsg": data.get("errmsg")})
        return WechatOAuthIdentity(openid=str(data["openid"]), unionid=data.get("unionid"))


class WechatOfficialAccountClient:
    """Service-account adapter.

    Actual message/template types depend on the verified account's enabled capabilities.
    The payload is therefore scene driven and template IDs are supplied through config.
    """

    def __init__(self) -> None:
        self._access_token: str | None = None
        self._expires_at: datetime | None = None

    def gate0_diagnostics(self) -> dict[str, Any]:
        configured = bool(settings.wechat_app_id and settings.wechat_app_secret)
        return {
            "configured": configured,
            "dev_mock": settings.wechat_dev_mock,
            "oauth_redirect_uri": settings.wechat_oauth_redirect_uri,
            "base_url_https": settings.app_base_url.startswith("https://") or settings.app_env != "production",
            "message_adapter": "MOCK" if settings.wechat_dev_mock else "OFFICIAL_ACCOUNT",
        }

    def send_scene_message(self, *, openid: str, scene: str, title: str, body: str, url: str | None, template_id: str | None = None) -> WechatSendResult:
        if settings.wechat_dev_mock:
            return WechatSendResult(success=True, message_id=f"mock-{scene.lower()}")
        if not template_id:
            return WechatSendResult(success=False, error_code="TEMPLATE_NOT_CONFIGURED", error_message="消息模板未配置")
        token = self._token()
        payload = {
            "touser": openid,
            "template_id": template_id,
            "url": url,
            "data": {
                "first": {"value": title},
                "keyword1": {"value": scene},
                "keyword2": {"value": body},
                "remark": {"value": "点击查看详情"},
            },
        }
        response = httpx.post(f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={token}", json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("errcode", 0) != 0:
            return WechatSendResult(success=False, error_code=str(data.get("errcode")), error_message=str(data.get("errmsg")))
        return WechatSendResult(success=True, message_id=str(data.get("msgid")))

    def _token(self) -> str:
        if self._access_token and self._expires_at and self._expires_at > datetime.now(timezone.utc) + timedelta(minutes=5):
            return self._access_token
        if not settings.wechat_app_id or not settings.wechat_app_secret:
            raise AppError("WECHAT_NOT_CONFIGURED", "微信公众号尚未配置", 503)
        response = httpx.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={"grant_type": "client_credential", "appid": settings.wechat_app_id, "secret": settings.wechat_app_secret},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        if "access_token" not in data:
            raise AppError("WECHAT_TOKEN_FAILED", "获取微信访问令牌失败", 502, data)
        self._access_token = data["access_token"]
        self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in", 7200)))
        return self._access_token

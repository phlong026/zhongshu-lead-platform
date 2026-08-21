from __future__ import annotations

from pydantic import BaseModel, Field


class LoginBody(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class InviteCreateBody(BaseModel):
    expires_hours: int = Field(default=72, ge=1, le=168)


class WechatMockCallbackBody(BaseModel):
    confirmation_intent: str = Field(min_length=32, max_length=8192)
    openid: str = Field(default="dev-openid-001", min_length=4, max_length=128)
    unionid: str | None = Field(default=None, max_length=128)
    nickname: str = Field(default="微信加盟商", min_length=1, max_length=128)
    avatar_url: str | None = Field(default=None, max_length=2048)
    subscribed: bool = False


class PasswordResetBody(BaseModel):
    new_password: str = Field(min_length=12, max_length=128)

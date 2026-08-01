from __future__ import annotations

from pydantic import BaseModel, Field


class LoginBody(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class InviteCreateBody(BaseModel):
    expires_hours: int = Field(default=72, ge=1, le=720)


class WechatMockCallbackBody(BaseModel):
    invite_token: str = Field(min_length=16)
    openid: str = Field(default="dev-openid-001", min_length=4, max_length=128)
    nickname: str = Field(default="微信加盟商")


class PasswordResetBody(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class LoginBody(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class ChangeOwnPasswordBody(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ChangeOwnUsernameBody(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    username: str = Field(min_length=2, max_length=64)

    @field_validator("username")
    @classmethod
    def reject_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("登录账号首尾不能有空格")
        return value


class InviteCreateBody(BaseModel):
    expires_hours: int = Field(default=72, ge=1, le=720)


class InviteConfirmStartBody(BaseModel):
    """H5 邀请页用户确认后换取绑定授权意图的请求体。"""

    invite: str = Field(min_length=16, max_length=128)
    return_url: str = Field(default="/h5/#/home", max_length=512)


class InvitePreviewBody(BaseModel):
    invite: str = Field(min_length=16, max_length=128)


class WechatMockCallbackBody(BaseModel):
    state: str = Field(min_length=20, max_length=4096)
    openid: str = Field(default="dev-openid-001", min_length=4, max_length=128)
    nickname: str = Field(default="微信加盟商")


class PasswordResetBody(BaseModel):
    new_password: str = Field(max_length=128)

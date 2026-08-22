from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class InvitePreviewBody(BaseModel):
    invite_token: str = Field(min_length=16, max_length=512)


class InviteConfirmStartBody(BaseModel):
    invite_token: str = Field(min_length=16, max_length=512)
    return_url: str = Field(default="/h5/#/home", min_length=1, max_length=512)
    accepted_agreement: bool

    @model_validator(mode="after")
    def require_active_confirmation(self) -> "InviteConfirmStartBody":
        if self.accepted_agreement is not True:
            raise ValueError("必须勾选协议并主动确认绑定")
        return self


class InviteDeliveryBody(BaseModel):
    channel: Literal["COPY", "QRCODE", "SMS", "WECHAT_MESSAGE"]
    recipient: str | None = Field(default=None, max_length=256)


class VerifiedPhoneMatchBody(BaseModel):
    verified_phone: str = Field(min_length=7, max_length=32)
    verification_source: Literal["TEST_DOUBLE", "TRUSTED_SERVER_ADAPTER"]


class ManualMatchConfirmBody(BaseModel):
    company_id: str = Field(min_length=1, max_length=36)
    confirmed: bool

    @model_validator(mode="after")
    def require_confirmation(self) -> "ManualMatchConfirmBody":
        if self.confirmed is not True:
            raise ValueError("必须明确确认匹配结果")
        return self


class ManualCompanySubmissionBody(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=128)
    owner_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, min_length=7, max_length=32)
    region_code: str = Field(min_length=2, max_length=32)
    notes: str | None = Field(default=None, max_length=1000)

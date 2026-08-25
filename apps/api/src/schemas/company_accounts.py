from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class CompanyAccountCreateBody(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str | None = Field(default=None, max_length=128)
    display_name: str = Field(min_length=1, max_length=64)
    role_code: str = Field(pattern=r"^(FRANCHISE_OWNER|FRANCHISE_EMPLOYEE)$")
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("username", "display_name")
    @classmethod
    def reject_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("账号和姓名首尾不能有空格")
        return value


class CompanyAccountReasonBody(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class CompanyAccountPasswordBody(CompanyAccountReasonBody):
    new_password: str | None = Field(default=None, max_length=128)

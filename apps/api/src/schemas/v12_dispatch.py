from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ManualDispatchBody(BaseModel):
    company_id: str = Field(min_length=1, max_length=36)
    idempotency_key: str = Field(min_length=8, max_length=128)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("company_id", "idempotency_key")
    @classmethod
    def strip_required(cls, value: str) -> str:
        return value.strip()


class ClaimBody(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)


class InternalAssignmentBody(BaseModel):
    employee_user_id: str | None = Field(default=None, min_length=1, max_length=36)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("employee_user_id", "reason")
    @classmethod
    def strip_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

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

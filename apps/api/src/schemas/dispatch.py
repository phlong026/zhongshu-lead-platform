from __future__ import annotations

from pydantic import BaseModel, Field


class DispatchBody(BaseModel):
    company_id: str
    idempotency_key: str = Field(min_length=8, max_length=128)
    reason: str | None = Field(default=None, max_length=500)


class ReleaseAssignmentBody(BaseModel):
    reason: str = Field(min_length=2, max_length=500)

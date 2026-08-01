from __future__ import annotations

from pydantic import BaseModel, Field


class ClaimBody(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)

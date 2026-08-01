from __future__ import annotations

from pydantic import BaseModel, Field


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)


class IdempotencyBody(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)

from __future__ import annotations

from pydantic import BaseModel, Field


class ReturnDraftBody(BaseModel):
    reason_code: str = Field(min_length=2, max_length=64)
    description: str = Field(min_length=5, max_length=500)


class ReturnReviewBody(BaseModel):
    decision: str = Field(pattern=r"^(APPROVE|REJECT|NEED_MORE)$")
    note: str = Field(min_length=2, max_length=500)

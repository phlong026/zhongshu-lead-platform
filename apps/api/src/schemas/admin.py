from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SystemConfigCreateBody(BaseModel):
    domain: str = Field(min_length=1, max_length=64)
    key: str = Field(min_length=1, max_length=128)
    value: dict[str, Any]
    publish_immediately: bool = False


class SystemConfigPublishBody(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class DashboardQuery(BaseModel):
    days: int = Field(default=7, ge=1, le=90)

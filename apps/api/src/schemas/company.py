from __future__ import annotations

from pydantic import BaseModel, Field


class CompanyCreateBody(BaseModel):
    code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=2, max_length=128)
    owner_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    level_code: str = Field(default="V1", max_length=32)
    region_codes: list[str] = Field(default_factory=list)
    capabilities: list[dict[str, str | None]] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=500)


class CompanyUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    owner_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    level_code: str | None = Field(default=None, max_length=32)
    status: str | None = Field(default=None, pattern=r"^(ACTIVE|DISABLED|PENDING)$")
    region_codes: list[str] | None = None
    capabilities: list[dict[str, str | None]] | None = None
    notes: str | None = Field(default=None, max_length=500)


class DictionaryItemBody(BaseModel):
    domain: str = Field(min_length=2, max_length=64)
    code: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    sort_order: int = 0
    metadata: dict = Field(default_factory=dict)
    active: bool = True

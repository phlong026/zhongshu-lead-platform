from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class CompanyCreateBody(BaseModel):
    code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=2, max_length=128)
    owner_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    level_code: str = Field(default="V1", max_length=32)
    region_codes: list[str] = Field(default_factory=list)
    capabilities: list[dict[str, str | None]] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=500)


class CompanySimpleCreateBody(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    owner_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    level_code: str = Field(default="V1", max_length=32)
    primary_city_code: str = Field(min_length=1, max_length=32)
    district_codes: list[str] = Field(default_factory=list)
    serve_all_districts: bool = True
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("primary_city_code")
    @classmethod
    def clean_primary_city_code(cls, value: str) -> str:
        return value.strip()

    @field_validator("district_codes")
    @classmethod
    def clean_district_codes(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(code.strip() for code in value if code.strip()))

class CompanyUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    owner_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    level_code: str | None = Field(default=None, max_length=32)
    status: str | None = Field(default=None, pattern=r"^(ACTIVE|DISABLED|PENDING)$")
    region_codes: list[str] | None = None
    capabilities: list[dict[str, str | None]] | None = None
    notes: str | None = Field(default=None, max_length=500)


class CompanyDeleteBody(BaseModel):
    confirmation_code: str = Field(min_length=2, max_length=32)


class DictionaryItemBody(BaseModel):
    domain: str = Field(min_length=2, max_length=64)
    code: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    sort_order: int = 0
    metadata: dict = Field(default_factory=dict)
    active: bool = True

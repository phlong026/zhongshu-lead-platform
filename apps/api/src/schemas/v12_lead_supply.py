from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class LeadDraftBody(BaseModel):
    customer_name: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    province: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    district: str | None = Field(default=None, max_length=64)
    region_code: str | None = Field(default=None, max_length=32)
    category_code: str | None = Field(default=None, max_length=64)
    brand_code: str | None = Field(default=None, max_length=64)
    source_channel: str | None = Field(default=None, max_length=64)
    need_summary: str | None = Field(default=None, max_length=2000)
    budget_min: int | None = Field(default=None, ge=0)
    budget_max: int | None = Field(default=None, ge=0)
    acquisition_cost_cents: int | None = Field(default=None, ge=0)
    consent_confirmed: bool = False

    @model_validator(mode="after")
    def validate_budget(self) -> "LeadDraftBody":
        if self.budget_min is not None and self.budget_max is not None and self.budget_min > self.budget_max:
            raise ValueError("预算上限不能低于预算下限")
        return self


class LeadDraftUpdateBody(BaseModel):
    customer_name: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    province: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    district: str | None = Field(default=None, max_length=64)
    region_code: str | None = Field(default=None, max_length=32)
    category_code: str | None = Field(default=None, max_length=64)
    brand_code: str | None = Field(default=None, max_length=64)
    source_channel: str | None = Field(default=None, max_length=64)
    need_summary: str | None = Field(default=None, max_length=2000)
    budget_min: int | None = Field(default=None, ge=0)
    budget_max: int | None = Field(default=None, ge=0)
    acquisition_cost_cents: int | None = Field(default=None, ge=0)
    consent_confirmed: bool | None = None


class SupplierReviewBody(BaseModel):
    decision: str = Field(pattern=r"^(APPROVE|REJECT)$")
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("decision")
    @classmethod
    def normalize_decision(cls, value: str) -> str:
        return value.upper()


class DedupOverrideBody(BaseModel):
    event_id: str | None = None
    reason: str = Field(min_length=5, max_length=1000)


class CapabilityRequestBody(BaseModel):
    capability_code: str = Field(pattern=r"^(LEAD_SUPPLIER|LEAD_RECEIVER)$")

    @field_validator("capability_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()


class CapabilityReviewBody(BaseModel):
    decision: str = Field(pattern=r"^(APPROVE|REJECT)$")
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("decision")
    @classmethod
    def normalize_decision(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def require_rejection_note(self) -> "CapabilityReviewBody":
        if self.decision == "REJECT" and not (self.note and self.note.strip()):
            raise ValueError("驳回公司能力申请时必须填写原因")
        return self


class ServiceAreaReplaceBody(BaseModel):
    region_codes: list[str] = Field(min_length=1, max_length=100)
    primary_city_code: str = Field(min_length=1, max_length=32)

    @field_validator("region_codes")
    @classmethod
    def normalize_region_codes(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        return list(dict.fromkeys(cleaned))

    @field_validator("primary_city_code")
    @classmethod
    def normalize_primary_city(cls, value: str) -> str:
        return value.strip()


class ServiceAreaReviewBody(BaseModel):
    decision: str = Field(pattern=r"^(APPROVE|REJECT)$")
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("decision")
    @classmethod
    def normalize_decision(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def require_rejection_note(self) -> "ServiceAreaReviewBody":
        if self.decision == "REJECT" and not (self.note and self.note.strip()):
            raise ValueError("驳回服务区域申请时必须填写原因")
        return self

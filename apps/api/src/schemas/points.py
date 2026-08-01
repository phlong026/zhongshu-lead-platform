from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PointsPackageBody(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=128)
    cash_amount_cents: int = Field(ge=0)
    base_points: int = Field(gt=0)
    bonus_points: int = Field(default=0, ge=0)
    level_code: str = Field(default="V1", max_length=32)
    entitlements: dict = Field(default_factory=dict)
    publish: bool = True
    effective_at: datetime | None = None
    expires_at: datetime | None = None


class PriceRuleBody(BaseModel):
    region_code: str | None = Field(default=None, max_length=32)
    category_code: str | None = Field(default=None, max_length=64)
    brand_code: str | None = Field(default=None, max_length=64)
    level_code: str | None = Field(default=None, max_length=32)
    points_cost: int = Field(gt=0)
    priority: int = Field(default=100, ge=0, le=10000)
    publish: bool = True
    effective_at: datetime | None = None
    expires_at: datetime | None = None


class RechargeBody(BaseModel):
    company_id: str
    package_id: str
    external_reference: str = Field(min_length=3, max_length=128)
    cash_amount_cents: int = Field(ge=0)
    note: str | None = Field(default=None, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=128)


class ManualAdjustmentBody(BaseModel):
    company_id: str
    delta: int
    reason: str = Field(min_length=3, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=128)


class ReverseLedgerBody(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=128)

from __future__ import annotations

from pydantic import BaseModel, Field


class MockFeishuRecordBody(BaseModel):
    record_id: str = Field(min_length=1, max_length=128)
    fields: dict


class FeishuMockSyncBody(BaseModel):
    records: list[MockFeishuRecordBody]
    field_mapping: dict[str, str] = Field(
        default_factory=lambda: {
            "customer_name": "客户姓名",
            "phone": "手机号",
            "province": "省",
            "city": "市",
            "district": "区县",
            "region_code": "地区编码",
            "category_code": "业务类目",
            "brand_code": "品牌",
            "source_channel": "来源渠道",
            "need_summary": "客户需求",
            "budget_min": "预算下限",
            "budget_max": "预算上限",
            "acquisition_cost": "获客成本",
        }
    )


class LeadStagingUpdateBody(BaseModel):
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


class DuplicateDecisionBody(BaseModel):
    duplicate_lead_id: str
    decision: str = Field(pattern=r"^(CONFIRMED|NOT_DUPLICATE|KEEP_FIRST|KEEP_CURRENT)$")

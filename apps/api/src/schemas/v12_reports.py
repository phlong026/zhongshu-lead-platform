from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator


class LeadExportRequestBody(BaseModel):
    created_from: datetime | None = None
    created_to: datetime | None = None
    source_kind: str | None = Field(default=None, max_length=32)
    receiver_company_id: str | None = Field(default=None, max_length=36)
    lead_status: str | None = Field(default=None, max_length=32)
    assignment_status: str | None = Field(default=None, max_length=32)
    assigned_by_user_id: str | None = Field(default=None, max_length=36)
    idempotency_key: str = Field(min_length=8, max_length=64)

    @field_validator(
        "source_kind",
        "receiver_company_id",
        "lead_status",
        "assignment_status",
        "assigned_by_user_id",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @field_validator("source_kind", "lead_status", "assignment_status")
    @classmethod
    def normalize_codes(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @field_validator("created_from", "created_to")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("日期时间必须包含时区")
        return value.astimezone(timezone.utc)

    @field_validator("idempotency_key")
    @classmethod
    def normalize_idempotency_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("幂等键不能为空")
        return normalized

    @model_validator(mode="after")
    def validate_window(self) -> "LeadExportRequestBody":
        if self.created_from and self.created_to and self.created_from > self.created_to:
            raise ValueError("创建时间起始不能晚于结束时间")
        return self

    def filters(self) -> dict[str, str | None]:
        return {
            "created_from": self.created_from.isoformat() if self.created_from else None,
            "created_to": self.created_to.isoformat() if self.created_to else None,
            "source_kind": self.source_kind,
            "receiver_company_id": self.receiver_company_id,
            "lead_status": self.lead_status,
            "assignment_status": self.assignment_status,
            "assigned_by_user_id": self.assigned_by_user_id,
        }

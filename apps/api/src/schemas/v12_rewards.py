from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class SupplierRewardRuleBody(BaseModel):
    ratio_bps: int = Field(default=3000, ge=1, le=10000)
    min_points: int = Field(default=0, ge=0)
    max_points: int | None = Field(default=None, ge=0)
    hard_duplicate_days: int = Field(default=90, ge=1)
    reward_duplicate_days: int = Field(default=180, ge=2)
    historical_suspect_days: int = Field(default=365, ge=3)
    publish_immediately: bool = False

    @model_validator(mode="after")
    def validate_ranges(self) -> "SupplierRewardRuleBody":
        if self.max_points is not None and self.max_points < self.min_points:
            raise ValueError("奖励最高值不能低于最低值")
        if not (
            self.hard_duplicate_days
            < self.reward_duplicate_days
            < self.historical_suspect_days
        ):
            raise ValueError("去重窗口必须严格递增")
        return self

    def rule_values(self) -> dict[str, int | None]:
        return self.model_dump(exclude={"publish_immediately"})


class SupplierRewardRulePublishBody(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class SupplierRewardReversalBody(BaseModel):
    reason_code: str = Field(min_length=2, max_length=32)
    note: str = Field(min_length=5, max_length=1000)

    @field_validator("reason_code")
    @classmethod
    def validate_reason_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"FRAUD", "SYSTEM_ERROR", "ADMIN_ERROR"}:
            raise ValueError("冲正原因仅支持欺诈、系统错误或管理员错误")
        return normalized

    @field_validator("note", mode="before")
    @classmethod
    def strip_note(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SupplierRewardSettleBody(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)
    note: str = Field(min_length=3, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def strip_note(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SupplierRewardSettleOneBody(BaseModel):
    note: str = Field(min_length=3, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def strip_note(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

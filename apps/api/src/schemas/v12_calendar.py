from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator


CALENDAR_SOURCES = frozenset({"MANUAL", "OFFICIAL", "IMPORT"})


class CalendarDayBody(BaseModel):
    is_workday: bool
    holiday_name: str | None = Field(default=None, max_length=128)
    source: str = Field(default="MANUAL", min_length=1, max_length=32)
    version: int = Field(default=1, ge=1)

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in CALENDAR_SOURCES:
            raise ValueError(
                "source 必须为 MANUAL、OFFICIAL 或 IMPORT"
            )
        return normalized

    @field_validator("holiday_name")
    @classmethod
    def normalize_holiday_name(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        return normalized or None


class CalendarDayImportItem(CalendarDayBody):
    day: date


class CalendarDayImportBody(BaseModel):
    days: list[CalendarDayImportItem] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_unique_days(self) -> "CalendarDayImportBody":
        values = [item.day for item in self.days]
        if len(values) != len(set(values)):
            raise ValueError("工作日历导入中存在重复日期")
        return self

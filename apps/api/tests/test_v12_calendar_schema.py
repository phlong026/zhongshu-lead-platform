from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from apps.api.src.schemas.v12_calendar import CalendarDayImportBody


def test_calendar_import_schema_rejects_duplicate_days() -> None:
    with pytest.raises(ValidationError, match="重复日期"):
        CalendarDayImportBody.model_validate(
            {
                "days": [
                    {"day": date(2026, 10, 1), "is_workday": False},
                    {"day": date(2026, 10, 1), "is_workday": False},
                ]
            }
        )


def test_calendar_source_is_normalized() -> None:
    body = CalendarDayImportBody.model_validate(
        {"days": [{"day": date(2026, 10, 1), "is_workday": False, "source": " official "}]}
    )
    assert body.days[0].source == "OFFICIAL"


def test_calendar_text_fields_are_normalized_and_source_is_restricted() -> None:
    body = CalendarDayImportBody.model_validate(
        {
            "days": [
                {
                    "day": date(2026, 10, 1),
                    "is_workday": False,
                    "holiday_name": "  国庆节  ",
                    "source": " official ",
                }
            ]
        }
    )
    assert body.days[0].holiday_name == "国庆节"

    with pytest.raises(ValidationError, match="source"):
        CalendarDayImportBody.model_validate(
            {
                "days": [
                    {
                        "day": date(2026, 10, 1),
                        "is_workday": False,
                        "source": "spreadsheet-v3",
                    }
                ]
            }
        )

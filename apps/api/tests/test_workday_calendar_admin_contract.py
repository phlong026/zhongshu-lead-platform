from __future__ import annotations

from pathlib import Path


ADMIN_APP = Path("apps/admin/public/app.js")


def _calendar_source() -> str:
    source = ADMIN_APP.read_text(encoding="utf-8")
    return source[
        source.index("function calendarDayModal") : source.index("const roleLabels")
    ]


def test_calendar_page_uses_backend_effective_days_and_china_timezone() -> None:
    source = ADMIN_APP.read_text(encoding="utf-8")
    calendar = _calendar_source()

    assert "can('calendar.read')" in source
    assert "Asia/Shanghai" in source
    assert "/admin/v1.2/calendar-days?start=" in calendar
    assert "item.is_override" in calendar
    assert "updated_by_name" in source
    assert "calendarFallbackWorkday" not in calendar
    assert "DEFAULT_WEEKDAY" in source
    assert "DEFAULT_WEEKEND" in source


def test_calendar_page_separates_read_manage_and_import_permissions() -> None:
    calendar = _calendar_source()

    assert "can('calendar.manage')" in calendar
    assert "can('calendar.import')" in calendar
    assert "calendar-new" in calendar
    assert "calendar-import" in calendar
    assert "\u65e0\u7ef4\u62a4\u6743\u9650" in calendar
    assert "\u65e0\u5bfc\u5165\u6743\u9650" in calendar


def test_calendar_writes_are_idempotent_and_explain_impact_scope() -> None:
    source = ADMIN_APP.read_text(encoding="utf-8")
    calendar = _calendar_source()

    assert "method:'PUT'" in calendar
    assert "method:'POST'" in calendar
    assert "created_count" in calendar
    assert "updated_count" in calendar
    assert "unchanged_count" in calendar
    assert "\u53ea\u5f71\u54cd\u4fdd\u5b58\u540e\u65b0\u9886\u53d6\u6216\u5386\u53f2\u7f3a\u5931\u5b57\u6bb5\u8865\u7b97" in source
    assert "\u5df2\u56fa\u5316\u7684\u5386\u53f2\u622a\u6b62\u65f6\u95f4\u4e0d\u56de\u7b97" in source
    assert "OFFICIAL" in calendar
    assert "MANUAL" in calendar
    assert "IMPORT" in calendar

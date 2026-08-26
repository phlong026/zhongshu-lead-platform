from __future__ import annotations

from pathlib import Path


ADMIN_APP = Path("apps/admin/public/v12-operations.js")


def _calendar_source() -> str:
    source = ADMIN_APP.read_text(encoding="utf-8")
    return source[
        source.index("function calendarDayModal") : source.index("const internalUserRoles")
    ]


def test_calendar_page_uses_backend_effective_days_and_china_timezone() -> None:
    source = ADMIN_APP.read_text(encoding="utf-8")
    calendar = _calendar_source()

    assert "settings:['平台设置','settings',['*'],true]" in source
    assert "Asia/Shanghai" in source
    assert "/admin/v1.2/calendar-days?start=" in calendar
    assert "item.is_override" in calendar
    assert "updated_by_name" in source
    assert "calendarFallbackWorkday" not in calendar
    assert "DEFAULT_WEEKDAY" not in source
    assert "DEFAULT_WEEKEND" not in source


def test_calendar_page_uses_default_rules_without_import_controls() -> None:
    calendar = _calendar_source()

    assert "data-view=\"settings\"" in calendar
    assert "calendar-new" in calendar
    assert "can('calendar.import')" not in calendar
    assert "calendar-import" not in calendar
    assert "calendar-source" not in calendar
    assert "calendar-version" not in calendar
    assert "法定节假日和调休只维护单日例外" in calendar


def test_calendar_writes_are_idempotent_and_explain_impact_scope() -> None:
    source = ADMIN_APP.read_text(encoding="utf-8")
    calendar = _calendar_source()

    assert "method:'PUT'" in calendar
    assert "method:'POST'" not in calendar
    assert "created_count" not in calendar
    assert "updated_count" not in calendar
    assert "unchanged_count" not in calendar
    assert "\u53ea\u5f71\u54cd\u4fdd\u5b58\u540e\u65b0\u9886\u53d6\u6216\u5386\u53f2\u7f3a\u5931\u5b57\u6bb5\u8865\u7b97" in source
    assert "\u5df2\u56fa\u5316\u7684\u5386\u53f2\u622a\u6b62\u65f6\u95f4\u4e0d\u56de\u7b97" in source
    assert "source:'MANUAL'" not in calendar
    assert "version:item.version||1" not in calendar

from pathlib import Path


def test_unified_desktop_settings_use_business_language_and_only_necessary_controls() -> None:
    source = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")
    settings = source[source.index("async function settings") : source.index("async function companies")]

    assert "系统设置" in settings
    assert "内部账号" in settings
    assert "工作日历" in settings
    assert "加盟商治理" in settings
    assert "底层参数" in settings
    assert "旧版入口" in settings
    for technical_copy in ("飞书暂存区", "JSON值", "元数据", "配置版本", "权限矩阵"):
        assert technical_copy not in settings


def test_calendar_keeps_default_rules_visible_without_import_controls() -> None:
    source = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")
    calendar = source[source.index("function calendarDayModal") : source.index("const internalUserRoles")]

    assert "默认按周一到周五计算工作日" in calendar
    assert "单日设定" in calendar
    assert "calendar-days" in calendar
    assert "calendar-import" not in calendar
    assert "calendar-source" not in calendar
    assert "calendar-version" not in calendar

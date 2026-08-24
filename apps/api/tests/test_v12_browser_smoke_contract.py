from __future__ import annotations

from pathlib import Path


SMOKE_SCRIPT = Path("scripts/browser_smoke_v12.py")


def test_browser_smoke_covers_admin_franchise_and_telesales_surfaces() -> None:
    script = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert 'results["admin"]' in script
    assert 'results["h5"]' in script
    assert 'results["call"]' in script
    assert "def _call_smoke(" in script
    assert 'page.goto(f"{base_url}/admin/index.html#/users"' in script
    assert 'page.wait_for_selector(".ops-shell", timeout=15000)' in script
    assert 'page.wait_for_selector(".layout", timeout=15000)' not in script
    assert 'page.goto(f"{base_url}/admin/index.html#/calendar"' in script
    assert 'input[name="u-role"]' in script
    assert 'input[value="FRANCHISE_OWNER"]' in script
    assert '"internal_role_count"' in script
    assert "v12-admin-internal-users.png" in script
    assert "v12-admin-workday-calendar.png" in script
    assert "--calendar-write-smoke" in script
    assert "--browser-executable" in script
    assert "calendar_write_smoke" in script
    assert "仅限隔离临时数据库" in script
    assert "#calendar-grid" in script
    assert "#calendar-import" in script
    assert "#calendar-import-text" in script
    assert 'select_option("OFFICIAL")' in script
    assert '"source": "IMPORT"' in script
    assert '"username": "operation"' in script
    assert '"password": "Operation123!"' in script
    assert "v12-admin-workday-calendar-readonly.png" in script
    assert '"calendar_readonly"' in script
    assert "无维护权限" in script
    assert "无导入权限" in script
    assert "page.go_back()" in script
    assert "page.go_forward()" in script
    assert "v12-admin-system-settings.png" in script
    assert 'data-system-setting="calendar"' in script
    assert 'data-system-setting="users"' in script
    assert 'data-system-setting="configs"' in script
    assert '"system_settings_visible"' in script
    assert '"browser_history_valid"' in script
    assert "telesales" in script
    assert "Telesales123!" in script
    assert 'page.goto(f"{base_url}/call/"' in script
    assert "v12-call-home-mobile.png" in script
    assert '"task_count"' in script
    assert "暂无待办任务" in script
    assert "_assert_no_visible_error(page" in script
    assert "MOBILE_WIDTHS = (320, 375, 390, 414)" in script
    assert "def _assert_responsive_widths(" in script
    assert '"responsive_widths"' in script
    assert "document.documentElement.scrollWidth" in script

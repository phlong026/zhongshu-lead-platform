from __future__ import annotations

from pathlib import Path


SMOKE_SCRIPT = Path("scripts/browser_smoke_v12.py")


def test_browser_smoke_covers_only_the_formal_role_workbenches() -> None:
    script = SMOKE_SCRIPT.read_text(encoding="utf-8")

    for scenario in ('"admin"', '"operation"', '"platform_h5"', '"h5"', '"call"'):
        assert scenario in script
    for function in ("def _admin_smoke", "def _operation_smoke", "def _platform_h5_smoke", "def _h5_smoke", "def _call_smoke"):
        assert function in script
    for formal_entry in (
        "/admin/v12-operations.html",
        "/h5/admin/",
        "/h5/v12-workbench.html",
        "/h5/call/",
    ):
        assert formal_entry in script
    for forbidden_legacy_surface in (
        "/admin/index.html",
        "#calendar-grid",
        "data-system-setting",
        "--calendar-write-smoke",
    ):
        assert forbidden_legacy_surface not in script
    assert "MOBILE_WIDTHS = (320, 375, 390, 414)" in script
    assert "def _assert_responsive_widths" in script
    assert "def _assert_safe_html_boundary" in script
    assert "franchise owner H5 must keep five focused bottom tabs" in script
    assert "franchise employee H5 must keep four focused bottom tabs" in script
    assert "franchise owner H5 bottom navigation must stay on one row" in script
    assert "telesales H5 bottom navigation must stay on one row" in script
    assert "telesales primary action must keep contrast" in script
    assert 'for view in ("overview", "leads", "companies", "finance"):' in script
    assert "super admin is missing permitted {view} navigation" in script
    assert "super admin can see restricted {view} navigation" in script
    assert 'page.wait_for_selector("#company-filter-form"' in script
    assert 'page.wait_for_selector(".company-review"' not in script
    assert script.count('page.locator(".ops-account-zone .ops-account-card").click()') == 3
    assert 'page.locator("#account-username")' in script
    assert 'page.wait_for_selector("#new-franchise-company"' in script
    assert 'page.get_by_role("heading", name="平台设置")' in script
    assert "data-account-tool=\"settings\"" not in script
    assert 'data-view="users"' in script
    assert "view=users" in script
    assert "内部账号" in script
    assert 'data-view="calendar"' in script
    assert "view=calendar" in script
    assert "工作日历" in script

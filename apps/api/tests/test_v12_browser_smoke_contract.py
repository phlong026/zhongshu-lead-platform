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

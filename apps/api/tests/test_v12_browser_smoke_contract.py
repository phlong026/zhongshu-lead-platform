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
    assert 'input[name="u-role"]' in script
    assert 'input[value="FRANCHISE_OWNER"]' in script
    assert '"internal_role_count"' in script
    assert "v12-admin-internal-users.png" in script
    assert "telesales" in script
    assert "Telesales123!" in script
    assert 'page.goto(f"{base_url}/call/"' in script
    assert "v12-call-home-mobile.png" in script
    assert '"task_count"' in script
    assert "暂无待办任务" in script
    assert "_assert_no_visible_error(page" in script

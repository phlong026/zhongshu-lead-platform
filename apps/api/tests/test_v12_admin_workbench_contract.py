from __future__ import annotations

from pathlib import Path


WORKBENCH = Path("apps/admin/public/v12-operations.js")
ENTRY = Path("apps/admin/public/v12-operations.html")


def test_desktop_workbench_uses_role_specific_navigation_and_lower_left_entrypoints() -> None:
    source = WORKBENCH.read_text(encoding="utf-8")

    assert "ADMIN_VIEW_CONTRACT" in source
    assert "SUPER_ADMIN:['overview','leads','companies','finance']" in source
    assert "OPERATION:['overview','leads','telesales','dispatch','companies']" in source
    assert 'data-account-center' in source
    assert 'data-account-tool' in source
    assert 'data-account-settings' not in source
    assert "S.me?.username||'当前账号'" in source
    assert "ops-account-zone" in source
    assert "ops-personal-menu" not in source
    assert "ops-top" not in source[source.index("function shell"):source.index("function firstAllowedView")]
    assert "${setting}" not in source[source.index("function shell"):source.index("function firstAllowedView")]


def test_desktop_workbench_uses_the_unified_brand_without_a_visible_version_suffix() -> None:
    entry = ENTRY.read_text(encoding="utf-8")
    source = WORKBENCH.read_text(encoding="utf-8")

    assert "客资管理平台" in entry
    assert "客资管理平台" in source
    assert "合家美宅 · 客资运营台" not in entry
    assert "V1.2 统一工作台" not in source

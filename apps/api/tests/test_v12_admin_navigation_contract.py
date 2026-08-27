from __future__ import annotations

import re
from pathlib import Path


OPERATIONS_JS = Path("apps/admin/public/v12-operations.js")


def _source() -> str:
    return OPERATIONS_JS.read_text(encoding="utf-8")


def test_v12_operations_uses_browser_history_for_internal_views() -> None:
    source = _source()
    go_function = re.search(r"function go\(view,id=''\)\{(?P<body>.*?)\n\}", source, re.DOTALL)

    assert go_function is not None
    assert "history.pushState" in go_function.group("body")
    assert "history.replaceState" not in go_function.group("body")
    assert "window.addEventListener('popstate'" in source
    assert "syncRouteFromUrl" in source


def test_v12_operations_exposes_only_formal_five_role_navigation() -> None:
    source = _source()

    for view in ("overview", "leads", "telesales", "dispatch", "companies", "returns", "finance", "audit"):
        assert f"{view}:" in source
    for legacy_marker in ("SYSTEM_LINKS", "data-system-setting", "index.html#"):
        assert legacy_marker not in source
    assert "ops-account-zone" in source
    assert "data-account-center" in source
    assert "ops-top-actions" not in source
    assert "ops-personal-menu" not in source
    assert "data-account-tool" in source
    assert "company.account.manage" in source
    assert "/points/recharge" in source


def test_v12_operations_does_not_use_the_authenticated_admin_redirect_as_back_link() -> None:
    source = _source()

    assert 'href="./"' not in source
    assert "返回后台" not in source


def test_admin_navigation_does_not_reopen_legacy_business_mutations() -> None:
    source = _source()

    for legacy_mutation in (
        "/verification/tasks",
        "/dispatch/leads/",
        "/leads/feishu/mock-sync",
        "/claims/assignments/",
    ):
        assert legacy_mutation not in source

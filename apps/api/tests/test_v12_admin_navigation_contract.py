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


def test_v12_operations_exposes_permission_scoped_system_settings() -> None:
    source = _source()

    assert "const SYSTEM_LINKS=" in source
    for href in (
        "./index.html#/users",
        "./index.html#/companies",
        "./index.html#/points",
        "./index.html#/recharge",
        "./index.html#/ledgers",
        "./index.html#/calendar",
        "./index.html#/configs",
    ):
        assert href in source

    for permission in (
        "company.read",
        "points.read",
        "points.package.manage",
        "points.recharge",
        "calendar.read",
        "*",
    ):
        assert permission in source

    assert "data-system-setting" in source
    assert "旧业务写接口" not in source
    assert "配置值与场景参数" not in source


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

from __future__ import annotations

from pathlib import Path


def test_admin_shell_keeps_account_and_navigation_available_on_mobile() -> None:
    html = Path("apps/admin/public/v12-operations.html").read_text(encoding="utf-8")
    js = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")
    css = Path("apps/admin/public/v12-operations.css").read_text(encoding="utf-8")

    assert "viewport-fit=cover" in html
    assert "ops-mobile-head" in js
    assert "ops-mobile-account" in js
    assert "safe-area-inset-bottom" in css
    assert ".ops-mobile-head{display:none}" in css


def test_admin_tables_become_labelled_cards_on_narrow_screens() -> None:
    js = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")
    css = Path("apps/admin/public/v12-operations.css").read_text(encoding="utf-8")

    assert "function enhanceResponsiveTables" in js
    assert "cell.dataset.label" in js
    assert ".ops-table thead{display:none}" in css
    assert ".ops-table td:before" in css
    assert "content:attr(data-label)" in css


def test_admin_forms_modals_and_actions_fit_phone_width() -> None:
    css = Path("apps/admin/public/v12-operations.css").read_text(encoding="utf-8")

    assert ".ops-filter>.ops-input" in css
    assert ".ops-modal{width:100%" in css
    assert "min-height:44px" in css
    assert ".ops-card-head{flex-direction:column;" in css

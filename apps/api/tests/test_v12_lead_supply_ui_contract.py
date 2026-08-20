from __future__ import annotations

import re
from pathlib import Path


def _references(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    return re.findall(r'(?:src|href)=["\']([^"\']+)["\']', content)


def _assert_local_references_exist(html: Path) -> None:
    content = html.read_text(encoding="utf-8")
    assert "https://" not in content and "http://" not in content
    for reference in _references(html):
        if reference.startswith(("#", "data:", "/api/")):
            continue
        path = reference.split("?", 1)[0]
        if path.startswith("/h5/"):
            target = Path("apps/h5/public") / path.removeprefix("/h5/")
        else:
            target = html.parent / path.lstrip("./")
        assert target.exists(), f"missing {reference} from {html}"


def test_admin_and_h5_shells_expose_v12_entry_scripts() -> None:
    admin_index = Path("apps/admin/public/index.html").read_text(encoding="utf-8")
    h5_index = Path("apps/h5/public/index.html").read_text(encoding="utf-8")
    assert "v12-entry-link.js" in admin_index
    assert "v12-supplier-entry.js" in h5_index
    assert Path("apps/admin/public/v12-entry-link.js").exists()
    assert Path("apps/h5/public/v12-supplier-entry.js").exists()


def test_dedicated_v12_pages_are_self_contained() -> None:
    _assert_local_references_exist(Path("apps/admin/public/v12-leads.html"))
    _assert_local_references_exist(Path("apps/h5/public/supplier.html"))


def test_admin_lead_supply_ui_uses_v12_flow_without_pre_verification() -> None:
    js = Path("apps/admin/public/v12-leads.js").read_text(encoding="utf-8")
    assert "返回工作台首页" in js
    assert "返回管理后台" not in js
    assert "/v1.2/platform/leads" in js
    assert "/v1.2/admin/supplier-leads" in js
    assert "/master-data/regions" in js
    assert "READY_DISPATCH" in js
    assert "/verification/tasks" not in js
    assert "LEAD_VERIFY" not in js
    assert "前置电销核验任务" in js


def test_supplier_h5_supports_capability_upload_list_and_detail() -> None:
    js = Path("apps/h5/public/supplier.js").read_text(encoding="utf-8")
    assert "/v1.2/company/capabilities" in js
    assert "/v1.2/supplier/leads" in js
    assert "LEAD_SUPPLIER" in js
    assert "consent_confirmed" in js
    assert "save-submit" in js
    assert "3 个工作日奖励观察期" in js
    assert "/verification/tasks" not in js

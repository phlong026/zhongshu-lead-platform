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
    assert "返回岗位首页" in js
    assert "返回工作台首页" not in js
    assert "返回管理后台" not in js
    assert "/v1.2/platform/leads" in js
    assert "/v1.2/admin/supplier-leads" in js
    assert "/master-data/regions" in js
    assert "READY_DISPATCH" in js
    assert "/verification/tasks" not in js
    assert "LEAD_VERIFY" not in js
    assert "前置电销核验任务" not in js
    assert "疑似重复的客资会交由人工复核" in js


def test_supplier_h5_supports_capability_upload_list_and_detail() -> None:
    js = Path("apps/h5/public/supplier.js").read_text(encoding="utf-8")
    assert "/v1.2/company/capabilities" in js
    assert "/v1.2/supplier/leads" in js
    assert "LEAD_SUPPLIER" in js
    assert "consent_confirmed" in js
    assert "save-submit" in js
    assert "<strong>合家美宅</strong>" in js
    assert "加盟商供客" in js
    assert "上传第一条客资" in js
    assert "手机号仅用于客资去重和业务联系" in js
    assert "重新编辑时请再次填写完整手机号" in js
    assert "HMAC" not in js
    assert "90/180/365" not in js
    assert "/verification/tasks" not in js


def test_supplier_h5_validates_before_creating_a_submission_draft() -> None:
    js = Path("apps/h5/public/supplier.js").read_text(encoding="utf-8")
    save_form = js.split("async function saveForm", 1)[1].split("async function deleteDraft", 1)[0]

    assert "validateSubmission(payload)" in save_form
    assert save_form.index("validateSubmission(payload)") < save_form.index("api('/v1.2/supplier/leads'")
    assert "form-error-summary" in js
    assert "data-field-error" in js
    assert "aria-invalid" in js
    assert "normalizePhone" in js


def test_supplier_h5_exposes_draft_cleanup_and_rejected_lead_revision() -> None:
    js = Path("apps/h5/public/supplier.js").read_text(encoding="utf-8")
    router = Path("apps/api/src/routers/v12_lead_supply.py").read_text(encoding="utf-8")

    assert re.search(r"method:\s*['\"]DELETE['\"]", js)
    assert "/revise" in js
    assert '@router.delete("/supplier/leads/{lead_id}")' in router
    assert '@router.post("/supplier/leads/{lead_id}/revise")' in router


def test_supplier_workbench_uses_user_facing_reward_copy() -> None:
    js = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")

    assert "奖励说明" in js
    assert "领取时规则快照" not in js
    assert "JSON.stringify(x.rule_snapshot" not in js

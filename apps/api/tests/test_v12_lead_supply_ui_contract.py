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


def test_formal_desktop_and_h5_shells_expose_their_workbench_scripts() -> None:
    admin = Path("apps/admin/public/v12-operations.html").read_text(encoding="utf-8")
    h5 = Path("apps/h5/public/v12-workbench.html").read_text(encoding="utf-8")

    assert "v12-operations.js" in admin
    assert "v12-workbench.js" in h5
    assert not Path("apps/admin/public/index.html").exists()
    assert not Path("apps/h5/public/index.html").exists()


def test_unified_operations_and_h5_shells_are_self_contained() -> None:
    _assert_local_references_exist(Path("apps/admin/public/v12-operations.html"))
    _assert_local_references_exist(Path("apps/h5/public/v12-workbench.html"))


def test_unified_operations_lead_ui_distinguishes_platform_and_supplier_flow() -> None:
    js = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")
    assert "/v1.2/platform/leads" in js
    assert "/v1.2/admin/supplier-leads" in js
    assert "/master-data/regions" in js
    assert "READY_DISPATCH" in js
    assert "data-platform-pre-dispatch" in js
    assert "请先补充客户联系电话，再派发电话核验" in js
    assert "平台补充资料后再处理" in js
    assert "platformLeadPage" in js
    assert "supplierLeadPage" in js
    assert "leadQueuePager" in js
    assert "加盟商来源才可退回加盟商补正" in js


def test_operations_review_exposes_four_initial_decisions_and_one_step_telesales_assignment() -> None:
    source = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")

    for decision in ("QUALIFIED", "INFO_INCOMPLETE", "DUPLICATE", "INVALID"):
        assert decision in source
    assert "pre_dispatch_reason" in source
    assert "信息不全并派发电销" in source


def test_supplier_h5_supports_capability_upload_list_and_detail() -> None:
    js = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")
    assert "/v1.2/company/capabilities" in js
    assert "/v1.2/supplier/leads" in js
    assert "LEAD_SUPPLIER" in js
    assert "consent_confirmed" in js
    assert "supply-submit" in js
    assert "加盟商工作台" in js
    assert "供资" in js
    assert "上传第一条客资" in js
    assert "客户知晓其联系方式和需求将用于业务对接" in js
    assert "请根据运营说明补正资料后重新提交" in js
    assert "HMAC" not in js
    assert "90/180/365" not in js
    assert "/verification/tasks" not in js


def test_supplier_h5_validates_before_creating_a_submission_draft() -> None:
    js = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")
    save_form = js.split("async function saveSupplyLead", 1)[1].split("async function openSupplyForm", 1)[0]

    assert "validateSupplySubmission(payload)" in save_form
    assert save_form.index("validateSupplySubmission(payload)") < save_form.index("api('/v1.2/supplier/leads'")
    assert "supply-form-error" in js
    assert "data-supply-field" in js
    assert "aria-invalid" in js
    assert "normalizeSupplyPhone" in js


def test_supplier_h5_exposes_draft_cleanup_and_rejected_lead_revision() -> None:
    js = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")
    router = Path("apps/api/src/routers/v12_lead_supply.py").read_text(encoding="utf-8")

    assert re.search(r"method:\s*['\"]DELETE['\"]", js)
    assert "/revise" in js
    assert '@router.delete("/supplier/leads/{lead_id}")' in router
    assert '@router.post("/supplier/leads/{lead_id}/revise")' in router


def test_supplier_h5_explains_operation_requested_rework_before_resubmission() -> None:
    source = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")

    assert "PRE_DISPATCH_REWORK_REQUIRED" in source
    assert "根据运营说明补正" in source
    assert "PENDING_TELESALES_VERIFY" in source
    assert "PENDING_OPERATION_DISPOSITION" in source


def test_supplier_workbench_uses_user_facing_reward_copy() -> None:
    js = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")

    assert "奖励说明" in js
    assert "领取时规则快照" not in js
    assert "JSON.stringify(x.rule_snapshot" not in js

from __future__ import annotations

from pathlib import Path


def test_v12_workbench_exposes_company_profile_flow() -> None:
    html = Path("apps/h5/public/v12-workbench.html").read_text(encoding="utf-8")
    js = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")

    assert "/v1.2/company/capabilities" in js
    assert "/v1.2/company/service-areas" in js
    assert "LEAD_RECEIVER" in js
    assert "LEAD_SUPPLIER" in js
    assert "review_note" in js
    assert "/master-data/regions" in js
    assert "company.profile.manage" in js
    assert "service-area-submit" in js
    assert "service-area-empty" in js
    assert "WORKBENCH_REPORT_PERMISSIONS" in js
    assert "defaultWorkbenchView" in js
    assert "canView" in js
    assert "effectiveAreas" in js
    assert "待移除区域在审核前仍生效" in js
    assert "company.profile.manage" in js
    assert "points.own.read" in js
    assert "v12-workbench.js?v=20260826-workflow-refresh" in html


def test_v12_operations_exposes_company_review_queue() -> None:
    html = Path("apps/admin/public/v12-operations.html").read_text(encoding="utf-8")
    js = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")

    assert "/v1.2/admin/company-capabilities" in js
    assert "/v1.2/admin/service-areas" in js
    assert "company.profile.review" in js
    assert "company-review" in js
    assert "审核申请" in js
    assert "company_name" in js
    assert "review_note" in js
    assert "review_status" in js
    assert "新建加盟商主体" in js
    assert "new-franchise-region-picker" in js
    assert "new-franchise-region-panel" in js
    assert "new-franchise-district-options" in js
    assert "province_code:province.code" in js
    assert "district_codes" in js
    assert "serve_all_districts:false" in js
    assert "v12-operations.js?v=20260826-workflow-refresh" in html


def test_stage6_company_review_and_internal_collaboration_actions_are_role_scoped() -> None:
    admin = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")
    franchise = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")

    assert "data-company-profile-approve" not in admin
    assert "一键审核" not in admin
    assert "后续提交的能力或服务区域变更" in admin
    assert "/account-directory" in franchise
    assert "/internal-assignee" in franchise
    assert "公司内部直接分配，无需运营审批" in franchise
    assert "负责人自己跟进" in franchise


def test_stage7_return_and_redispatch_actions_keep_the_business_closure_explicit() -> None:
    admin = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")
    franchise = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")

    assert "FOLLOWUP_INVALID_REQUIRES_RETURN" in franchise
    assert "error.code=j.code" in franchise
    assert "下一步：发起退回" in franchise
    assert "data-return-evidence" in franchise
    assert "补充证据" in franchise
    assert "资金影响" in admin
    assert "x.status==='REVIEWING'&&verification.conclusion" in admin
    assert "RETURNED_RECEIVER_EXCLUDED" in admin
    assert "return_receiver_override" in admin


def test_stage8_finance_governance_stays_inside_the_unified_workbench() -> None:
    admin = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")

    for marker in (
        "/points/adjust",
        "/points/ledgers/${encodeURIComponent(ledgerId)}/reverse",
        "/points/reconciliation/${encodeURIComponent(companyId)}",
        "/points/packages?active_only=false",
        "/points/price-rules",
        "/v1.2/supplier-rewards",
        "ledger.type",
        "financeRewardPage",
        "收款核验与凭证说明",
        "结算说明",
        "对账异常",
        "无需第二位超级管理员复核",
    ):
        assert marker in admin

    assert "function rewards" not in admin

from __future__ import annotations

from pathlib import Path


def test_v12_workbench_exposes_company_profile_flow() -> None:
    html = Path("apps/h5/public/v12-workbench.html").read_text(encoding="utf-8")
    js = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")
    entry = Path("apps/h5/public/v12-workbench-entry.js").read_text(encoding="utf-8")

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
    assert "company.profile.manage" in entry
    assert "points.own.read" in entry
    assert "followup.own.manage" not in entry
    assert "v12-workbench.js?v=20260825-stage6-collaboration" in html


def test_v12_operations_exposes_company_review_queue() -> None:
    html = Path("apps/admin/public/v12-operations.html").read_text(encoding="utf-8")
    js = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")
    entry = Path("apps/admin/public/v12-entry-link.js").read_text(encoding="utf-8")

    assert "/v1.2/admin/company-capabilities" in js
    assert "/v1.2/admin/service-areas" in js
    assert "company.profile.review" in js
    assert "company.profile.review" in entry
    assert "company-review" in js
    assert "审核申请" in js
    assert "company_name" in js
    assert "review_note" in js
    assert "review_status" in js
    assert "v12-operations.js?v=20260825-stage6-collaboration" in html


def test_stage6_company_review_and_internal_collaboration_actions_are_role_scoped() -> None:
    admin = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")
    franchise = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")

    assert "/profile/approve-pending" in admin
    assert "一键审核" in admin
    assert "待移除区域仍需单独审核" in admin
    assert "/account-directory" in franchise
    assert "/internal-assignee" in franchise
    assert "公司内部直接分配，无需运营审批" in franchise
    assert "负责人自己跟进" in franchise

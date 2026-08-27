from pathlib import Path


def test_workbench_brand_identity_and_message_entry_are_consistent() -> None:
    admin_html = Path("apps/admin/public/v12-operations.html").read_text(encoding="utf-8")
    admin_js = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")
    h5_html = Path("apps/h5/public/v12-workbench.html").read_text(encoding="utf-8")
    h5_js = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")

    for source in (admin_html, admin_js, h5_html, h5_js):
        assert "客资管理平台" in source
        assert "合家美宅统一工作台" not in source
    assert "FRANCHISE_OWNER:'加盟商'" in admin_js
    assert "ops-message-badge" in admin_js
    assert "wb-message-badge" in h5_js
    assert "账号中心" not in admin_js.split("function account()", 1)[1].split("function changeOwnUsername", 1)[0]


def test_admin_dashboard_uses_the_decision_and_finance_dashboard_endpoints() -> None:
    source = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")

    assert "/v1.2/reports/management-dashboard" in source
    assert "/v1.2/reports/finance-dashboard" in source
    for marker in ("新增客资", "有效完成率", "待结算奖励", "客资新增趋势", "流转漏斗"):
        assert marker in source
    for marker in (
        "加盟商积分充值",
        "发起充值",
        "当前剩余积分",
        "近 ${S.financeDays} 天净充值",
        "累计净充值",
        "已冲正",
        "充值记录",
    ):
        assert marker in source
    for marker in ("ops-company-detail-compact", "ops-company-summary-grid", "最多显示 4 条"):
        assert marker in source

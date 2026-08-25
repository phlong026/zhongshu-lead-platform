from __future__ import annotations

from pathlib import Path


ADMIN_OPERATIONS = Path("apps/admin/public/v12-operations.js")
ADMIN_OPERATIONS_CSS = Path("apps/admin/public/v12-operations.css")
CALL_H5 = Path("apps/call-h5/public/app.js")
FRANCHISE_H5 = Path("apps/h5/public/v12-workbench.js")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_five_roles_have_only_their_formal_workbenches() -> None:
    source = "\n".join(_read(path) for path in (ADMIN_OPERATIONS, CALL_H5, FRANCHISE_H5))

    for role in (
        "SUPER_ADMIN",
        "OPERATION",
        "TELESALES",
        "FRANCHISE_OWNER",
        "FRANCHISE_EMPLOYEE",
    ):
        assert role in source

    for removed_role in ("LEAD_ENTRY", "RETURN_REVIEWER", "FINANCE"):
        assert removed_role not in source


def test_platform_workbench_keeps_identity_left_and_top_actions_operational() -> None:
    source = _read(ADMIN_OPERATIONS)

    assert "ops-side-foot" in source
    assert "ops-top-actions" in source
    for label in ("刷新", "设置", "退出"):
        assert label in source
    assert "data-view=\"companies\"" in source
    assert "index.html" not in source


def test_operation_workbench_has_the_required_dispatch_and_account_boundaries() -> None:
    source = _read(ADMIN_OPERATIONS)

    for marker in (
        "派发前置电销核验",
        "前置电销待处置",
        "运营处置电销结论",
        "派发退回电话核验",
        "派发或改派原因",
        "公司级状态",
        "不查看加盟商内部员工的客资分配明细",
    ):
        assert marker in source
    assert "/v1.2/admin/leads/" in source
    assert "/pre-dispatch-verification" in source
    assert "/pre-dispatch-disposition" in source
    assert "/v1.2/return-verifications/tasks/" in source


def test_superadmin_can_manage_franchise_accounts_and_recharge_with_audit_copy() -> None:
    source = _read(ADMIN_OPERATIONS)

    for marker in (
        "开通加盟商账号",
        "重置加盟商账号密码",
        "超级管理员操作必须填写至少",
        "仅展示一次",
        "线下充值",
        "外部收款凭据号",
        "无需第二位超级管理员复核",
    ):
        assert marker in source
    assert "/companies/${encodeURIComponent(companyId)}/accounts" in source
    assert "/points/recharge" in source
    assert "crypto.randomUUID()" in source


def test_franchise_and_telesales_h5_navigation_is_short_home_first_and_role_scoped() -> None:
    franchise = _read(FRANCHISE_H5)
    telesales = _read(CALL_H5)

    assert "FRANCHISE_HOME_CONTRACT" in franchise
    assert "['home','leads','points','profile']" in franchise
    for label in ("首页", "客资", "积分", "我的"):
        assert label in franchise
    assert "运营派发" in telesales
    assert "自主领取" in telesales
    assert "['home', 'home', '首页']" in telesales
    assert "['verify', 'phone', '核验']" in telesales
    assert "['records', 'history', '记录']" in telesales
    assert "['profile', 'user', '我的']" in telesales


def test_role_interfaces_keep_hejiameizhai_warm_visual_tokens_and_focus_states() -> None:
    source = _read(ADMIN_OPERATIONS_CSS)

    for color in ("#f8f5ef", "#f1e9dd", "#765d45", "#c9a66b", "#54845d", "#b74a43"):
        assert color in source.lower()
    assert ":focus-visible" in source
    assert "font-variant-numeric:tabular-nums" in source.replace(" ", "")

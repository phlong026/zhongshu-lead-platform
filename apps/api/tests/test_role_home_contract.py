from __future__ import annotations

import re
from pathlib import Path


ADMIN_APP = Path("apps/admin/public/app.js")
ADMIN_OPERATIONS = Path("apps/admin/public/v12-operations.js")
ADMIN_OPERATIONS_CSS = Path("apps/admin/public/v12-operations.css")
CALL_H5 = Path("apps/call-h5/public/app.js")
FRANCHISE_H5 = Path("apps/h5/public/v12-workbench.js")

FIXED_ROLES = (
    "SUPER_ADMIN",
    "OWNER",
    "LEAD_ENTRY",
    "OPERATION",
    "TELESALES",
    "FINANCE",
    "RETURN_REVIEWER",
    "FRANCHISE_OWNER",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_role_home_contract_declares_default_surface_for_all_fixed_roles() -> None:
    source = "\n".join(_read(path) for path in (ADMIN_APP, ADMIN_OPERATIONS, CALL_H5, FRANCHISE_H5))

    assert "ROLE_HOME_CONTRACT" in source
    for role in FIXED_ROLES:
        assert role in source
    for label in ("系统治理", "经营总览", "录入工作台", "今日运营", "电话核验", "积分财务", "退回审核", "加盟商工作台"):
        assert label in source


def test_multi_role_home_priority_prefers_dedicated_mobile_workbenches() -> None:
    source = _read(ADMIN_OPERATIONS)
    priority = re.search(r"ROLE_HOME_PRIORITY=\[(?P<body>[^\]]+)\]", source)

    assert priority is not None
    body = priority.group("body")
    for left, right in zip(FIXED_ROLES[:1] + ("OWNER", "OPERATION", "FINANCE", "LEAD_ENTRY", "RETURN_REVIEWER", "TELESALES"), ("OWNER", "OPERATION", "FINANCE", "LEAD_ENTRY", "RETURN_REVIEWER", "TELESALES", "FRANCHISE_OWNER")):
        assert body.index(left) < body.index(right)


def test_franchise_home_contract_uses_fixed_five_tab_bottom_navigation() -> None:
    source = _read(FRANCHISE_H5)

    assert "FRANCHISE_HOME_CONTRACT" in source
    assert "['home','leads','points','notifications','profile']" in source
    for label in ("首页", "客资", "积分", "消息", "我的"):
        assert label in source
    assert "公司资料与接单能力" in source
    assert "slice(0,5)" not in source
    assert "/points/accounts/" in source
    assert "encodeURIComponent(companyId)" in source
    assert "d.points" not in source


def test_telesales_home_contract_focuses_on_call_tasks_without_finance_copy() -> None:
    source = _read(CALL_H5)

    assert "TELESALES_HOME_CONTRACT" in source
    assert "page_size=200" in source
    assert "items.slice(0, 5)" in source
    for label in ("待处理", "核验中", "已提交", "开始核验", "优先任务"):
        assert label in source
    for finance_copy in ("公司充值", "平台收入", "加盟商积分"):
        assert finance_copy not in source


def test_admin_role_home_contract_separates_role_specific_first_screen_copy() -> None:
    source = _read(ADMIN_OPERATIONS)

    assert "ADMIN_ROLE_HOME_CONTENT" in source
    for label in (
        "风险预警",
        "账号角色",
        "今日运营",
        "待初审",
        "待派发",
        "待分配电销",
        "积分财务",
        "人工入账",
        "录入工作台",
        "疑似重复",
        "退回审核",
        "待补证",
    ):
        assert label in source
    for raw_copy in ("原始权限码", "JSON 快照", "模板快照"):
        assert raw_copy not in source


def test_admin_role_homes_use_existing_role_appropriate_data_sources() -> None:
    source = _read(ADMIN_OPERATIONS)

    assert "async function leadEntryHome" in source
    assert "/leads/staging?page=1&page_size=20" in source
    assert "async function returnReviewerHome" in source
    assert "/v1.2/returns?page=1&page_size=20" in source
    for permission in (
        "dashboard.business.read",
        "dashboard.operation.read",
        "dashboard.finance.read",
        "lead.manual.manage",
        "return.review",
    ):
        assert permission in source


def test_v12_operations_replaces_browser_prompts_with_branded_forms() -> None:
    source = _read(ADMIN_OPERATIONS)

    assert "function actionForm" in source
    assert "prompt(" not in source
    assert "confirm(" not in source
    for action in ("初审", "派发", "终审", "冲正"):
        assert action in source


def test_legacy_admin_danger_actions_use_branded_confirmations() -> None:
    source = _read(ADMIN_APP)

    assert "function confirmAction" in source
    assert "confirm(" not in source
    assert "modalRoot.appendChild(layer)" in source
    assert "layer.remove()" in source
    for action in ("清理历史暂存", "撤销邀请", "停用账号"):
        assert action in source


def test_role_interfaces_keep_hejiameizhai_warm_visual_tokens_and_focus_states() -> None:
    source = _read(ADMIN_OPERATIONS_CSS)

    for color in ("#f8f5ef", "#f1e9dd", "#765d45", "#c9a66b", "#54845d", "#b74a43"):
        assert color in source.lower()
    assert ":focus-visible" in source
    assert "font-variant-numeric:tabular-nums" in source.replace(" ", "")

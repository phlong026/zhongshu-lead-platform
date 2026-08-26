from __future__ import annotations

import re
from pathlib import Path


ADMIN = Path("apps/admin/public")
H5 = Path("apps/h5/public")
CALL_H5 = Path("apps/call-h5/public")


def _read(root: Path, filename: str) -> str:
    return (root / filename).read_text(encoding="utf-8")


def test_operations_pages_use_business_language_and_existing_safe_endpoints() -> None:
    source = _read(ADMIN, "v12-operations.js")
    for developer_copy in (
        "旧业务写接口",
        "配置值与场景参数",
        "请输入电销用户 ID",
        "JSON.stringify(x.evidences",
        "JSON.stringify(x.rule_snapshot",
        "奖励比例（基点）",
        "业务ID",
        "请求ID",
        "JSON.stringify(d,null,2)",
    ):
        assert developer_copy not in source
    assert "/admin-meta/telesales-users" in source
    assert "/return-evidences/${encodeURIComponent(item.id)}/download" in source
    assert "派发前置电销核验" in source
    assert "派发退回电话核验" in source
    assert "奖励比例（%）" in source
    assert "esc(label(x.source_kind))" in source
    assert "公司编号" not in source
    for field in (
        "currentRule.min_points",
        "currentRule.max_points",
        "currentRule.hard_duplicate_days",
        "currentRule.reward_duplicate_days",
        "currentRule.historical_suspect_days",
    ):
        assert field in source


def test_company_workbench_uses_user_language_and_real_unread_count() -> None:
    source = _read(H5, "v12-workbench.js")
    for developer_copy in (
        "能力编码",
        "领取与积分扣减原子执行",
        "领取时规则快照",
        "JSON.stringify(x.rule_snapshot",
        "按当前设备本地时间填写，提交时统一转换为标准时间",
    ):
        assert developer_copy not in source
    assert "unread_notifications" in source
    assert "x.read_at?'READ':'UNREAD'" in source
    assert "wb-message-entry" in source
    assert "wb-message-badge" in source
    assert "已读" in source
    assert "未读" in source
    assert "function safeDeepLink" in source
    assert "url.origin!==location.origin" in source


def test_company_workbench_opens_existing_legacy_assignment_message_links() -> None:
    source = _read(H5, "v12-workbench.js")

    assert "function legacyAssignmentLinkToken" in source
    assert "/claims/resolve-link?token=" in source
    assert "searchParams.set('view','assignments')" in source
    assert "history.replaceState(null,'',url)" in source


def test_dispatch_messages_use_the_v12_assignment_detail_route() -> None:
    source = Path("apps/api/src/services/dispatch_service.py").read_text(encoding="utf-8")

    assert 'deep_link = f"/h5/v12-workbench.html?view=assignments&id={assignment.id}"' in source
    assert "/h5/#/link/" not in source


def test_unified_lead_review_explains_outcomes_without_security_or_process_jargon() -> None:
    source = _read(ADMIN, "v12-operations.js")
    assert "HMAC" not in source
    assert "加盟商来源会直接进入待电销核实" in source
    assert "运营处置电销结论" in source


def test_call_workbench_shows_chinese_role_and_plain_task_language() -> None:
    source = _read(CALL_H5, "app.js")
    assert re.search(r"const\s+TELESALES_HOME_CONTRACT\s*=", source)
    assert "me.roles.join('、')" not in source
    assert "事实后置核验" not in source
    assert "自主领取" in source
    assert "电销人员" in source
    assert "工作范围" in source

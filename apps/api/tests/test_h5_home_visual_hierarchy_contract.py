from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_franchise_home_prioritizes_one_role_specific_action_before_secondary_metrics() -> None:
    source = read("apps/h5/public/v12-workbench.js")

    assert "franchiseHomeHero" in source
    assert "franchiseHomeMetrics" in source
    assert "homeTaskList" in source
    assert "HOME_ASSIGNMENT_STATUSES" in source
    assert "assignments?status=${status}" in source
    assert "待领取客资" in source
    assert "今日待跟进" in source
    assert "查看积分" in source
    assert "继续跟进" in source
    assert "greetingName" in source


def test_franchise_owner_home_prioritizes_available_points_and_keeps_rework_in_todos() -> None:
    source = read("apps/h5/public/v12-workbench.js")

    assert "labelText:'可用积分'" in source
    assert "actionLabel:'查看积分'" in source
    assert "view:'points'" in source
    assert "['待补资料',supplyRework" in source
    assert "labelText:'待补资料'" not in source


def test_franchise_profile_removes_platform_capability_display_and_moves_logout_to_my() -> None:
    source = read("apps/h5/public/v12-workbench.js")

    assert "CAPABILITY_META" not in source
    assert 'id="company-capabilities"' not in source
    assert 'id="wb-refresh"' not in source
    assert 'id="wb-logout"' not in source
    assert 'id="wb-profile-logout"' in source
    assert "经营区域" in source


def test_telesales_home_uses_the_same_mobile_priority_hierarchy() -> None:
    source = read("apps/call-h5/public/app.js")

    assert "callHomeHero" in source
    assert "callHomeMetrics" in source
    assert "homeTaskList" in source
    assert "今日待核验" in source
    assert "继续核验" in source
    assert "greetingName" in source


def test_platform_homes_use_one_role_specific_priority_card_and_compact_metrics() -> None:
    source = read("apps/admin/public/h5/app.js")

    assert "platformHomeHero" in source
    assert "platformHomeMetrics" in source
    assert "风险待办" in source
    assert "优先处理" in source
    assert "处理客资" in source
    assert "greetingName" in source

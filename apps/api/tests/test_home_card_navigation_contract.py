from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
H5 = ROOT / "apps" / "h5" / "public"
CALL = ROOT / "apps" / "call-h5" / "public"
ADMIN = ROOT / "apps" / "admin" / "public"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_franchise_home_metrics_open_existing_business_details() -> None:
    workbench = read(H5 / "v12-workbench.js")

    assert "leads:['供资','plus']" in workbench
    for route in ("points", "assignments", "returns"):
        assert f"view:'{route}'" in workbench
    assert "const followView='followups'" in workbench
    assert "view:'leads'" in workbench
    assert "franchiseHomeMetrics" in workbench
    assert "franchiseHomeHero" in workbench
    assert "homeTaskList" in workbench
    assert "account?.available_for_dispatch??account?.balance" in workbench
    assert "const taskView=owner&&waitingClaim?'assignments':followView" in workbench



def test_franchise_secondary_metrics_scroll_or_filter_to_existing_details() -> None:
    workbench = read(H5 / "v12-workbench.js")

    assert "scroll:'company-capabilities'" not in workbench
    assert "scroll:'service-areas'" not in workbench
    assert 'id="company-capabilities"' not in workbench
    assert 'id="service-areas"' in workbench
    assert "经营区域" in workbench
    assert "REWARD_FILTERS" in workbench
    for status in ("SETTLED", "OBSERVING", "FROZEN"):
        assert f"id:'{status}'" in workbench


def test_telesales_home_uses_actionable_count_and_clear_mobile_navigation() -> None:
    source = read(CALL / "app.js")

    for nav_item in (
        "['home', 'home', '首页']",
        "['verify', 'phone', '核验']",
        "['records', 'history', '记录']",
        "['profile', 'user', '我的']",
    ):
        assert nav_item in source
    assert "const actionable = tasks.filter" in source
    assert "actionable.length" in source
    assert "tasks.slice(0, 3).map(homeTaskRow)" in source
    assert "['待开始', metric(tasks, ['ASSIGNED']), 'verify?status=ASSIGNED']" in source
    assert "status === 'ASSIGNED'" in source
    assert "['ASSIGNED', '待开始']" in source


def test_supplier_submodule_navigation_uses_progress_and_upload_semantics() -> None:
    source = read(H5 / "v12-workbench.js")

    assert "leads:['供资','plus']" in source
    assert "提交后默认由电销核实" in source
    assert "上传第一条客资" in source
    assert "我的客资" not in source


def test_admin_dashboard_and_role_kpis_link_to_existing_detail_pages() -> None:
    operations = read(ADMIN / "v12-operations.js")

    for destination in (
        "leads",
        "telesales",
        "dispatch",
        "returns",
        "companies",
        "finance",
        "audit",
    ):
        assert f"{destination}:[" in operations

    assert "data-overview-view" in operations
    assert "go(button.dataset.overviewView)" in operations
    assert "index.html" not in operations
    for mapping in (
        "FOLLOWING:'跟进中'",
        "RETURN_PENDING:'退回处理中'",
        "RETURNED:'已退回'",
        "RELEASED:'已释放'",
        "EXPIRED:'已过期'",
        "COMPLETED:'已完成'",
    ):
        assert mapping in operations


def test_formal_admin_home_distinguishes_platform_and_operation_boundaries() -> None:
    source = read(ADMIN / "v12-operations.js")
    overview = source[source.index("async function overview"):source.index("async function review")]

    for copy in ("/v1.2/reports/management-dashboard", "客资新增与有效率趋势", "流转漏斗", "当前没有需要处理的异常待办"):
        assert copy in overview
    assert "经营风险" not in overview
    assert "statusSummary(" not in overview
    assert "ops-summary-columns" not in overview


def test_formal_lead_page_uses_the_unified_operation_view() -> None:
    source = read(ADMIN / "v12-operations.js")

    assert "async function review" in source
    assert "分配电销核实" in source
    assert "history.pushState" in source
    assert "window.addEventListener('popstate'" in source


def test_card_layout_uses_fluid_width_and_mobile_tap_targets() -> None:
    shared = read(H5 / "design-system-v13.css")
    workbench_css = read(H5 / "v12-workbench.css")
    call_css = read(CALL / "styles.css")
    admin_css = read(ADMIN / "v12-operations.css")

    assert "width:100%;max-width:var(--zs-client-max-width)" in shared
    assert "width:375px" not in shared
    assert ".wb-kpi[data-go]" in workbench_css
    assert "button.metric" in call_css
    assert ".ops-kpi" in admin_css
    for css in (workbench_css, call_css, admin_css):
        assert "focus-visible" in css

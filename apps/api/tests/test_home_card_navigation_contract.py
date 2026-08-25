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

    assert "leads:['客资','list']" in workbench
    for route in ("points", "assignments", "returns"):
        assert f"view:'{route}'" in workbench
    assert 'data-go="leads" data-id="supply"' in workbench
    assert "wb-action-value" in workbench
    assert "const heroMetrics=[]" in workbench
    assert "main:heroMetrics.length===0" in workbench
    assert "if(heroMetrics.length>4)heroMetrics.length=4" in workbench
    assert "account?.available_for_dispatch??account?.balance" in workbench
    assert "const rewardAttention=" in workbench
    assert "const rewardTotal=" in workbench
    assert "d.supplier_rewards?.points" not in workbench
    assert "const assignmentMetricTarget=canView('assignments')" in workbench



def test_franchise_secondary_metrics_scroll_or_filter_to_existing_details() -> None:
    workbench = read(H5 / "v12-workbench.js")

    assert "scroll:'company-capabilities'" in workbench
    assert "scroll:'service-areas'" in workbench
    assert 'id="company-capabilities"' in workbench
    assert 'id="service-areas"' in workbench
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
    assert "actionable.slice(0, 5)" in source
    assert 'data-route="verify?status=ASSIGNED"' in source
    assert "status === 'ASSIGNED'" in source
    assert "['ASSIGNED', '待开始']" in source


def test_supplier_submodule_navigation_uses_progress_and_upload_semantics() -> None:
    source = read(H5 / "supplier.js")

    assert "<h1>供客进度</h1>" in source
    assert "${supplierIcon('list')}" in source
    assert "${supplierIcon('plus')}" in source
    assert "供客进度" in source
    assert "我的客资" not in source


def test_admin_dashboard_and_role_kpis_link_to_existing_detail_pages() -> None:
    operations = read(ADMIN / "v12-operations.js")

    for destination in (
        "?view=leads",
        "?view=telesales",
        "?view=dispatch",
        "?view=returns",
        "?view=companies",
        "?view=finance",
        "?view=audit",
    ):
        assert destination in operations

    assert "data-overview-view" in operations
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


def test_formal_admin_home_explains_the_five_role_boundaries() -> None:
    source = read(ADMIN / "v12-operations.js")

    for copy in ("运营待办", "运营派发", "不具备自主领取", "不查看加盟商内部员工的客资分配明细"):
        assert copy in source


def test_formal_lead_page_uses_the_unified_operation_view() -> None:
    source = read(ADMIN / "v12-operations.js")

    assert "async function review" in source
    assert "派发电销核验" in source
    assert "history.pushState" in source
    assert "window.addEventListener('popstate'" in source


def test_card_layout_uses_fluid_width_and_mobile_tap_targets() -> None:
    shared = read(H5 / "design-system-v13.css")
    workbench_css = read(H5 / "v12-workbench.css")
    call_css = read(CALL / "styles.css")
    admin_css = read(ADMIN / "styles.css")

    assert "width:100%;max-width:var(--zs-client-max-width)" in shared
    assert "width:375px" not in shared
    assert ".wb-kpi[data-go]" in workbench_css
    assert "button.metric" in call_css
    assert "button.stat" in admin_css
    for css in (workbench_css, call_css, admin_css):
        assert "focus-visible" in css

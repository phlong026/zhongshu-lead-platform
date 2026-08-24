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
    legacy = read(H5 / "app.js")

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

    for route in (
        "leads?status=PENDING_CLAIM",
        "leads?status=ACTIVE",
        "leads?status=RETURN_PENDING",
        "leads?status=COMPLETED",
    ):
        assert f'data-route="{route}"' in legacy
    assert "filter === 'ACTIVE'" in legacy
    assert "['ACTIVE','待跟进']" in legacy


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
        "['tasks', 'phone', '核验']",
        "['profile', 'user', '我的']",
    ):
        assert nav_item in source
    assert "const actionableTasks = tasks.items.filter" in source
    assert "actionableTasks.length" in source
    assert "actionableTasks.slice(0, 5)" in source
    assert 'data-route="tasks?status=TODO"' in source
    assert "status === 'TODO'" in source
    assert "['TODO', '待开始']" in source


def test_supplier_submodule_navigation_uses_progress_and_upload_semantics() -> None:
    source = read(H5 / "supplier.js")

    assert "<h1>供客进度</h1>" in source
    assert "${supplierIcon('list')}" in source
    assert "${supplierIcon('plus')}" in source
    assert "供客进度" in source
    assert "我的客资" not in source


def test_admin_dashboard_and_role_kpis_link_to_existing_detail_pages() -> None:
    legacy = read(ADMIN / "app.js")
    operations = read(ADMIN / "v12-operations.js")

    assert "cards.map(([l,v,i,r])" in legacy
    for route in ("staging", "verification", "qualified", "assignments", "ledgers"):
        assert f"'{route}'" in legacy
    assert "alertCards" in legacy

    assert "function statusSummary(data,hrefForStatus)" in operations
    assert "typeof hrefForStatus==='function'" in operations
    assert 'class="ops-detail ops-detail-link"' in operations
    for destination in (
        "./v12-leads.html",
        "?view=dispatch",
        "?view=returns",
        "?view=companies",
        "./index.html#/outbox",
        "./index.html#/audit",
    ):
        assert destination in operations

    assert "./v12-leads.html?status=" in operations
    assert "./index.html#/assignments?status=" in operations
    assert "?view=returns&status=" in operations
    assert "status:S.status" in operations
    assert "const filter=query.get('status')||''" in legacy
    assert "status:filter" in legacy
    for mapping in (
        "FOLLOWING:'跟进中'",
        "RETURN_PENDING:'退回处理中'",
        "RETURNED:'已退回'",
        "RELEASED:'已释放'",
        "EXPIRED:'已过期'",
        "COMPLETED:'已完成'",
    ):
        assert mapping in operations


def test_remaining_admin_numeric_summaries_open_existing_details() -> None:
    source = read(ADMIN / "app.js")

    assert '<button type="button" class="stat" data-route="staging">' in source
    assert 'data-calendar-scroll="calendar-grid"' in source
    assert 'data-calendar-scroll="calendar-overrides"' in source
    assert "[data-calendar-scroll]" in source
    assert "scrollIntoView" in source


def test_platform_lead_summary_cards_apply_existing_status_filters() -> None:
    source = read(ADMIN / "v12-leads.js")

    assert 'data-platform-status=""' in source
    for status in ("DRAFT", "READY_DISPATCH", "DUPLICATE"):
        assert f'data-platform-status="{status}"' in source
    assert "[data-platform-status]" in source
    assert "function setPlatformStatus(status)" in source
    assert "history.pushState" in source
    assert "addEventListener('popstate'" in source
    for label in ("当前结果", "本页草稿", "本页待派发", "本页重复/疑似"):
        assert label in source


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

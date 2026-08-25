from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
H5 = ROOT / "apps" / "h5" / "public"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_design_system_version(html: str) -> str:
    m = re.search(r'design-system-v13\.css(?:\?v=)?([^"\']*)', html)
    assert m is not None, "design-system-v13.css 未命中"
    return m.group(1) or ""


def test_h5_bottom_nav_keeps_each_franchise_role_on_its_focused_workflow() -> None:
    app = read(H5 / "app.js")
    workbench = read(H5 / "v12-workbench.js")

    assert "['home','home','首页']" in app
    assert "['leads','list','客资']" in app
    assert "['points','coins','积分']" in app
    assert "['notifications','bell','消息']" not in app
    assert "['notifications','bell','消息']" not in workbench
    m = re.search(r"const FRANCHISE_NAV=(\{.*?\});\nconst VIEWS", workbench, re.S)
    assert m is not None
    nav = m.group(1)
    assert "notifications" not in nav
    assert "FRANCHISE_OWNER" in nav
    assert "FRANCHISE_EMPLOYEE" in nav
    assert "['home','home','首页'],['assignments','hand-claim','接收'],['leads','plus','供资'],['followups','clipboard-check','跟进'],['profile','user','我的']" in nav
    assert "['home','home','首页'],['followups','clipboard-check','跟进'],['leads','plus','供资'],['profile','user','我的']" in nav


def test_both_profile_pages_have_message_entry_and_unread_prompts() -> None:
    app = read(H5 / "app.js")
    workbench = read(H5 / "v12-workbench.js")

    assert 'data-profile-messages' in app
    assert "消息中心" in app
    assert "条未读" in app
    assert "api('/notifications?page=1&page_size=100')" in app
    assert "filter(item=>!item.read_at).length" in app

    assert "wb-profile-message" in workbench
    assert 'data-go="notifications"' in workbench
    assert "条未读" in workbench
    assert 'id="wb-msg"' not in workbench


def test_design_system_css_version_consistent_across_key_pages() -> None:
    index = read(H5 / "index.html")
    supplier = read(H5 / "supplier.html")
    workbench = read(H5 / "v12-workbench.html")

    index_v = extract_design_system_version(index)
    supplier_v = extract_design_system_version(supplier)
    workbench_v = extract_design_system_version(workbench)

    assert index_v == supplier_v == workbench_v
    assert "href=\"./design-system-v13.css" in index
    assert "href=\"./design-system-v13.css" in supplier
    assert "href=\"./design-system-v13.css" in workbench
    assert index.index("./status-pages-v13.css") < index.index("./design-system-v13.css")
    assert supplier.index("./supplier.css") < supplier.index("./design-system-v13.css")
    assert workbench.index("./v12-workbench.css") < workbench.index("./design-system-v13.css")


def test_shared_design_system_defines_client_shell_and_four_tab_navigation() -> None:
    css = read(H5 / "design-system-v13.css")

    for marker in (
        "--zs-client-max-width:520px",
        ".workbench-shell",
        ".supplier-app",
        ".wb-bottom",
        ".supplier-header",
        "grid-template-columns:repeat(4,1fr)",
        "env(safe-area-inset-bottom)",
    ):
        assert marker in css


def test_no_developer_copy_or_legacy_terms_in_main_profile_workbench_contracts() -> None:
    app = read(H5 / "app.js")
    workbench = read(H5 / "v12-workbench.js")

    for marker in (
        "开发模式",
        "JSON 数据",
        "JSON字段",
        "UUID 字段",
        "供应商工作台",
        "V1.2 契约",
        "高频操作",
        "最近 50 条按时间倒序展示",
    ):
        assert marker not in app
        assert marker not in workbench


def test_supplier_page_uses_brand_back_link_and_hides_redundant_progress_copy() -> None:
    supplier = read(H5 / "supplier.js")
    supplier_css = read(H5 / "supplier.css")
    shared_css = read(H5 / "design-system-v13.css")

    assert "<strong>合家美宅</strong>" in supplier
    assert "./v12-workbench.html?view=profile" in supplier
    assert "返回工作台" in supplier
    assert "当前账号：" not in supplier
    assert "返回客资助手" not in supplier
    assert "可查看详情了解当前进度" not in supplier
    assert "const progress = leadProgress(item)" in supplier
    assert "progress ?" in supplier
    assert "totalPages > 1" in supplier
    assert ".supplier-lead-top" in supplier_css
    assert "align-items: flex-start" in supplier_css
    assert "body.supplier-body" in shared_css


def test_profile_metrics_guard_prevents_duplicate_async_enhancement() -> None:
    profile = read(H5 / "profile-v13.js")

    assert "dataset.zsProfileMetrics" in profile
    assert "dataset.zsProfileMetrics='loading'" in profile
    assert "dataset.zsProfileMetrics='done'" in profile


def test_secondary_workbench_entries_live_in_profile_without_header_clutter() -> None:
    workbench_entry = read(H5 / "v12-workbench-entry.js")
    supplier_entry = read(H5 / "v12-supplier-entry.js")

    assert "v12-workbench-top" not in workbench_entry
    assert "supplier-workspace-top" not in supplier_entry
    assert "zs-v13-profile-action-icon" in workbench_entry
    assert "zs-v13-profile-action-icon" in supplier_entry

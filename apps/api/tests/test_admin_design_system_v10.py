from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADMIN = ROOT / "apps" / "admin" / "public"


def test_admin_v10_assets_loaded_before_application():
    index = (ADMIN / "index.html").read_text(encoding="utf-8")
    assert "./admin-design-system-v10.css" in index
    assert "./admin-design-system-v10.js" in index
    assert index.index("./styles.css") < index.index("./admin-design-system-v10.css")
    assert index.index("./admin-design-system-v10.js") < index.index("./app.js")


def test_admin_v10_design_tokens_and_page_ids():
    css = (ADMIN / "admin-design-system-v10.css").read_text(encoding="utf-8")
    js = (ADMIN / "admin-design-system-v10.js").read_text(encoding="utf-8")
    for token in ("--adm-brand:#7a6248", "--adm-gold:#c8a96a", "--adm-ivory:#f8f5ef"):
        assert token in css
    for selector in (".adm-v10-page-id", ".adm-v10-scope", ".adm-v10-overlay-id", ".adm-v10-login-security"):
        assert selector in css
    for number in range(1, 20):
        assert f"ADM-{number:02d}" in js


def test_admin_v10_preserves_role_and_finance_boundaries():
    js = (ADMIN / "admin-design-system-v10.js").read_text(encoding="utf-8")
    assert "admDashboardId" in js
    assert "main.page .stat .label" in js
    assert "const pageText=" not in js
    assert "仅展示资格状态，不展示具体积分余额" in js
    assert "现金在线下完成" in js
    assert "页面、接口、数据范围和字段权限必须同时生效" in js
    assert "MutationObserver" in js


def test_admin_v10_extended_operational_pages():
    index = (ADMIN / "index.html").read_text(encoding="utf-8")
    js = (ADMIN / "admin-extended-pages-v10.js").read_text(encoding="utf-8")
    assert "./admin-extended-pages-v10.js" in index
    assert "/master-data/regions" in js
    assert "/admin-meta/rbac-matrix" in js
    assert "/admin-meta/telesales-users" in js
    assert "/verification/tasks/${taskId}/reclaim" in js
    assert "/admin-meta/companies/${id}" in js
    assert "基础资料" in js

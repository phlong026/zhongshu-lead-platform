from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ADMIN = ROOT / "apps" / "admin" / "public"


def test_unified_desktop_assets_load_the_single_formal_operations_shell() -> None:
    entry = (ADMIN / "v12-operations.html").read_text(encoding="utf-8")

    assert "./v12-operations.css" in entry
    assert "./v12-operations.js" in entry
    assert entry.index("/h5/safe-html.js") < entry.index("./v12-operations.js")
    assert not (ADMIN / "index.html").exists()


def test_unified_desktop_shell_keeps_one_compact_account_entry() -> None:
    script = (ADMIN / "v12-operations.js").read_text(encoding="utf-8")
    css = (ADMIN / "v12-operations.css").read_text(encoding="utf-8")

    assert "ops-account-zone" in script
    assert "data-account-center" in script
    assert "data-account-settings" not in script
    assert "ops-account-tools" in script
    assert "S.me?.username||'当前账号'" in script
    assert "ops-top-actions" not in script
    assert "ops-personal-menu" not in script
    assert "ops-account-workspace" not in script
    assert "刷新账号状态" not in script
    assert "退出当前账号" in script
    assert "ops-account-zone" in css
    assert "ops-account-settings" not in css
    assert "ops-role-hero" in css
    assert "ops-trace-layout" in css


def test_unified_desktop_uses_svg_icons_without_legacy_v10_assets() -> None:
    script = (ADMIN / "v12-operations.js").read_text(encoding="utf-8")

    assert "window.ZSIconSystem?.svg" in script
    for icon_name in ("layout-dashboard", "phone", "user-check", "hand-claim", "building", "wallet", "calendar"):
        assert f"'{icon_name}'" in script
    assert not (ADMIN / "admin-design-system-v10.js").exists()
    assert not (ADMIN / "admin-extended-pages-v10.js").exists()

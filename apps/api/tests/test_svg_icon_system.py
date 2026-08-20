from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
H5 = ROOT / "apps" / "h5" / "public"
ADMIN = ROOT / "apps" / "admin" / "public"

GLYPHS = set("⌂▤◈◉♙⇩☎✓↗♟⚙⌁＋≋↩◇◷!×‹›☰⌕?▶●↻▦→◆")
ASSET_VERSION = "?v=20260820-clarity"
COMPANY_PROFILE_ASSET_VERSION = "?v=20260820-company-profile"


def test_all_h5_surfaces_load_local_svg_icon_system_before_application():
    entries = {
        "index.html": ("./app.js", ASSET_VERSION),
        "supplier.html": ("./supplier.js", ASSET_VERSION),
        "v12-workbench.html": ("./v12-workbench.js", COMPANY_PROFILE_ASSET_VERSION),
    }
    for filename, (application_script, application_version) in entries.items():
        index = (H5 / filename).read_text(encoding="utf-8")
        assert f"./svg-icon-system.css{ASSET_VERSION}" in index
        assert f"./svg-icon-system.js{ASSET_VERSION}" in index
        assert f"{application_script}{application_version}" in index
        assert index.index("./svg-icon-system.js") < index.index(application_script)


def test_all_admin_surfaces_reuse_same_local_svg_icon_system():
    entries = {
        "index.html": "./app.js",
        "v12-leads.html": "./v12-leads.js",
        "v12-operations.html": ("./v12-operations.js", COMPANY_PROFILE_ASSET_VERSION),
    }
    for filename, application in entries.items():
        application_script, application_version = (
            application if isinstance(application, tuple) else (application, ASSET_VERSION)
        )
        index = (ADMIN / filename).read_text(encoding="utf-8")
        assert f"/h5/svg-icon-system.css{ASSET_VERSION}" in index
        assert f"/h5/svg-icon-system.js{ASSET_VERSION}" in index
        assert f"{application_script}{application_version}" in index
        assert index.index("/h5/svg-icon-system.js") < index.index(application_script)


def test_svg_icon_system_is_inline_accessible_and_has_no_remote_dependency():
    js = (H5 / "svg-icon-system.js").read_text(encoding="utf-8")
    css = (H5 / "svg-icon-system.css").read_text(encoding="utf-8")
    assert "viewBox=\"0 0 24 24\"" in js
    assert "stroke-width=\"1.8\"" in js
    assert "aria-hidden=\"true\"" in js
    assert "focusable=\"false\"" in js
    assert "currentColor" in js
    assert "MutationObserver" in js
    assert "window.ZSIconSystem" in js
    assert "http://" not in js and "https://" not in js
    assert ".zs-svg-icon" in css
    for name in ("user-check", "hand-claim", "coins", "log-out", "award"):
        assert f"{name}:" in js or f"'{name}':" in js


def test_admin_uses_named_svg_icons_instead_of_unicode_placeholders():
    filenames = (
        "app.js",
        "ui.js",
        "admin-design-system-v10.js",
        "admin-extended-pages-v10.js",
        "v12-entry-link.js",
        "v12-leads.js",
        "v12-operations.js",
    )
    source = "\n".join((ADMIN / filename).read_text(encoding="utf-8") for filename in filenames)
    for glyph in "⌂▤◈◉♙⇩☎✓↗♟⚙⌁＋≋↩◇◷×‹›☰⌕▶●↻▦→◆":
        assert f"'{glyph}'" not in source
        assert f'"{glyph}"' not in source
    for name in ("inbox", "phone", "user-check", "hand-claim", "coins"):
        assert f"'{name}'" in source
    assert "window.ZSIconSystem?.svg" in source


def test_h5_composite_buttons_render_svg_directly():
    home = (H5 / "design-system-v13.js").read_text(encoding="utf-8")
    assert "window.ZSIconSystem?.svg" in home
    assert "zsIcon('bell')" in home
    assert "zsIcon('list')" in home
    assert "zsIcon('coins')" in home
    assert "zsIcon('clipboard-check')" in home
    assert "◉ 消息" not in home


def test_h5_profile_actions_use_svg_instead_of_css_unicode_content():
    js = (H5 / "profile-v13.js").read_text(encoding="utf-8")
    css = (H5 / "profile-v13.css").read_text(encoding="utf-8")
    assert "window.ZSIconSystem?.svg" in js
    for name in ("bell", "coins", "log-out"):
        assert f"'{name}'" in js
    assert "content:'◉'" not in css
    assert "content:'◈'" not in css
    assert "content:'↪'" not in css


def test_h5_v12_workbench_uses_named_svg_icons():
    js = (H5 / "v12-workbench.js").read_text(encoding="utf-8")
    assert "window.ZSIconSystem?.svg" in js
    for name in ("home", "inbox", "hand-claim", "rotate-ccw", "award", "bell"):
        assert f"'{name}'" in js
    for glyph in ("'⌂'", "'＋'", "'客'", "'↩'", "'◆'", "'●'"):
        assert glyph not in js


def test_h5_business_scripts_do_not_render_unicode_icon_placeholders():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in H5.glob("*.js")
        if path.name != "svg-icon-system.js"
    )
    for glyph in "⌂▤◈◉♙⇩☎✓↗♟⚙⌁＋≋↩◇◷×‹›☰⌕▶●↻▦→◆":
        assert glyph not in source, f"H5 business script still renders Unicode icon: {glyph}"
    for placeholder in ("<b>!</b>", "icon:'!'", "['warn','!'", "empty('!'"):
        assert placeholder not in source


def test_every_unicode_icon_used_by_web_frontends_is_covered():
    icon_system = (H5 / "svg-icon-system.js").read_text(encoding="utf-8")
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (H5, ADMIN)
        for path in root.glob("*.js")
        if path.name != "svg-icon-system.js"
    )
    used = {char for char in source if char in GLYPHS}
    missing = {char for char in used if f"'{char}'" not in icon_system}
    assert not missing, f"Unmapped Unicode icons: {sorted(missing)}"

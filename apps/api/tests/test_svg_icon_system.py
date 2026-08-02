from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
H5 = ROOT / "apps" / "h5" / "public"
ADMIN = ROOT / "apps" / "admin" / "public"

GLYPHS = set("⌂▤◈◉♙⇩☎✓↗♟⚙⌁＋≋↩◇◷!×‹›☰⌕?▶●↻")


def test_h5_loads_local_svg_icon_system_before_application():
    index = (H5 / "index.html").read_text(encoding="utf-8")
    assert "./svg-icon-system.css" in index
    assert "./svg-icon-system.js" in index
    assert index.index("./svg-icon-system.js") < index.index("./app.js")


def test_admin_reuses_same_local_svg_icon_system():
    index = (ADMIN / "index.html").read_text(encoding="utf-8")
    assert "/h5/svg-icon-system.css" in index
    assert "/h5/svg-icon-system.js" in index
    assert index.index("/h5/svg-icon-system.js") < index.index("./app.js")


def test_svg_icon_system_is_inline_accessible_and_has_no_remote_dependency():
    js = (H5 / "svg-icon-system.js").read_text(encoding="utf-8")
    css = (H5 / "svg-icon-system.css").read_text(encoding="utf-8")
    assert "viewBox=\"0 0 24 24\"" in js
    assert "aria-hidden=\"true\"" in js
    assert "focusable=\"false\"" in js
    assert "currentColor" in js
    assert "MutationObserver" in js
    assert "window.ZSIconSystem" in js
    assert "http://" not in js and "https://" not in js
    assert ".zs-svg-icon" in css


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

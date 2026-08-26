from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
H5 = ROOT / "apps" / "h5" / "public"
ADMIN = ROOT / "apps" / "admin" / "public"
CALL = ROOT / "apps" / "call-h5" / "public"
SVG_VERSION = "?v=20260820-clarity"


def test_formal_entries_load_the_local_svg_system_before_the_application() -> None:
    entries = (
        (H5 / "v12-workbench.html", "./v12-workbench.js"),
        (ADMIN / "v12-operations.html", "./v12-operations.js"),
        (ADMIN / "h5" / "index.html", "./app.js"),
        (CALL / "index.html", "./app.js"),
    )
    for entry, application_script in entries:
        source = entry.read_text(encoding="utf-8")
        assert f"svg-icon-system.css{SVG_VERSION}" in source
        assert "svg-icon-system.js" in source
        assert application_script in source
        assert source.index("svg-icon-system.js") < source.index(application_script)


def test_svg_icon_system_is_inline_accessible_and_has_no_remote_dependency() -> None:
    js = (H5 / "svg-icon-system.js").read_text(encoding="utf-8")
    css = (H5 / "svg-icon-system.css").read_text(encoding="utf-8")

    for marker in ('viewBox="0 0 24 24"', 'aria-hidden="true"', 'focusable="false"', "currentColor", "window.ZSIconSystem"):
        assert marker in js
    assert "http://" not in js and "https://" not in js
    assert ".zs-svg-icon" in css


def test_active_workbenches_use_named_svg_icons_instead_of_unicode_placeholders() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            H5 / "v12-workbench.js",
            ADMIN / "v12-operations.js",
            ADMIN / "h5" / "app.js",
            CALL / "app.js",
        )
    )

    assert "window.ZSIconSystem?.svg" in source
    for name in ("home", "phone", "user-check", "hand-claim", "coins", "log-out", "calendar"):
        assert f"'{name}'" in source or f'"{name}"' in source
    for glyph in "⌂▤◈◉♙⇩☎✓↗♟⚙⌁＋≋↩◇◷×‹›☰⌕▶●↻▦→◆":
        assert glyph not in source

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
H5 = ROOT / "apps" / "h5" / "public"


def test_h5_v13_assets_are_loaded_after_base_styles():
    index = (H5 / "index.html").read_text(encoding="utf-8")
    assert "./design-system-v13.css" in index
    assert "./design-system-v13.js" in index
    assert index.index("./styles.css") < index.index("./design-system-v13.css")
    assert index.index("./design-system-v13.js") < index.index("./app.js")


def test_h5_v13_design_tokens_and_home_patch_contract():
    css = (H5 / "design-system-v13.css").read_text(encoding="utf-8")
    js = (H5 / "design-system-v13.js").read_text(encoding="utf-8")
    for token in ("--zs-brand:#7a6248", "--zs-gold:#c8a96a", "--zs-ivory:#f8f5ef"):
        assert token in css
    for selector in (".zs-v13-home", ".zs-v13-point-card", ".zs-v13-quick", ".zs-v13-lead-section"):
        assert selector in css
    assert "function zsPatchHome" in js
    assert "data-zs-route" in js
    assert "MutationObserver" in js

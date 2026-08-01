from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
H5 = ROOT / "apps" / "h5" / "public"


def test_h5_v13_return_page_contract():
    index = (H5 / "index.html").read_text(encoding="utf-8")
    css = (H5 / "return-v13.css").read_text(encoding="utf-8")
    js = (H5 / "return-v13.js").read_text(encoding="utf-8")
    assert "./return-v13.css" in index
    assert "./return-v13.js" in index
    for selector in (".zs-v13-return-page", ".zs-v13-preview-grid", ".zs-v13-return-confirm"):
        assert selector in css
    assert "function zsPatchReturn" in js
    assert "#screenshot-files" in js
    assert "#audio-file" in js
    assert "#submit-return" in js

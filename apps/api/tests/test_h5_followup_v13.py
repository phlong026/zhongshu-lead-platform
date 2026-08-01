from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
H5 = ROOT / "apps" / "h5" / "public"


def test_h5_v13_followup_modal_contract():
    index = (H5 / "index.html").read_text(encoding="utf-8")
    css = (H5 / "followup-v13.css").read_text(encoding="utf-8")
    js = (H5 / "followup-v13.js").read_text(encoding="utf-8")
    assert "./followup-v13.css" in index
    assert "./followup-v13.js" in index
    for selector in ("#follow-modal .modal", ".zs-v13-follow-chips", ".zs-v13-follow-actions"):
        assert selector in css
    assert "function zsPatchFollowupModal" in js
    assert "#follow-status" in js
    assert "#save-follow" in js

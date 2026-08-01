from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
H5 = ROOT / "apps" / "h5" / "public"


def test_h5_v13_profile_patch_contract():
    index = (H5 / "index.html").read_text(encoding="utf-8")
    css = (H5 / "profile-v13.css").read_text(encoding="utf-8")
    js = (H5 / "profile-v13.js").read_text(encoding="utf-8")
    assert "./profile-v13.css" in index
    assert "./profile-v13.js" in index
    for selector in (".zs-v13-profile-page", ".zs-v13-company-card", ".zs-v13-profile-metrics"):
        assert selector in css
    assert "function zsPatchProfile" in js
    assert "/points/ledgers" in js
    assert "#logout" in js

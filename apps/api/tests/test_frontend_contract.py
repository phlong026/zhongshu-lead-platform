from __future__ import annotations

import re
from pathlib import Path


PUBLIC_ROOTS = [
    Path("apps/h5/public"),
    Path("apps/call-h5/public"),
    Path("apps/admin/public"),
]


def test_frontend_static_references_exist_and_are_self_contained():
    for root in PUBLIC_ROOTS:
        index = root / "index.html"
        content = index.read_text(encoding="utf-8")
        assert "https://" not in content and "http://" not in content, f"external runtime dependency in {index}"
        references = re.findall(r'(?:src|href)=["\']([^"\']+)["\']', content)
        for reference in references:
            if reference.startswith(("#", "data:", "/api/")):
                continue
            target = root / reference.split("?", 1)[0].lstrip("./")
            assert target.exists(), f"missing static reference {reference} from {index}"
        assert (root / "logo.png").exists()


def test_frontend_api_routes_match_backend_contract():
    combined = "\n".join((root / "app.js").read_text(encoding="utf-8") for root in PUBLIC_ROOTS)
    assert "/api/v1/claim/" not in combined
    assert "`/claims/" in combined or "'/claims/" in combined
    assert "`/returns/" in combined or "'/returns/" in combined
    assert "`/followups/" in combined or "'/followups/" in combined


def test_h5_has_no_online_payment_or_native_recording_claims():
    h5 = (Path("apps/h5/public/app.js").read_text(encoding="utf-8") + Path("apps/h5/public/index.html").read_text(encoding="utf-8"))
    prohibited = ["微信支付", "支付宝支付", "自动录音", "原路退款"]
    for text in prohibited:
        assert text not in h5

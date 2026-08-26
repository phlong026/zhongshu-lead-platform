from __future__ import annotations

import re
from pathlib import Path


FORMAL_ENTRIES = {
    Path("apps/admin/public/v12-operations.html"): Path("apps/admin/public"),
    Path("apps/admin/public/h5/index.html"): Path("apps/admin/public/h5"),
    Path("apps/call-h5/public/index.html"): Path("apps/call-h5/public"),
    Path("apps/h5/public/v12-workbench.html"): Path("apps/h5/public"),
}
MOUNTED_ROOTS = {
    "/h5/": Path("apps/h5/public"),
    "/admin/": Path("apps/admin/public"),
}


def _resolve_reference(root: Path, reference: str) -> Path:
    path = reference.split("?", 1)[0]
    for prefix, mounted_root in MOUNTED_ROOTS.items():
        if path.startswith(prefix):
            return mounted_root / path.removeprefix(prefix)
    return root / path.removeprefix("./")


def test_formal_workbench_entries_have_only_local_runtime_assets() -> None:
    for entry, root in FORMAL_ENTRIES.items():
        content = entry.read_text(encoding="utf-8")

        assert "http://" not in content and "https://" not in content, entry
        for reference in re.findall(r'(?:src|href)=["\']([^"\']+)["\']', content):
            if reference.startswith(("#", "data:", "/api/")):
                continue
            assert _resolve_reference(root, reference).is_file(), (entry, reference)


def test_franchise_workbench_is_the_only_h5_business_shell() -> None:
    source = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")

    for marker in (
        'id="franchise-login-form"',
        "FRANCHISE_NAV",
        "function openSupplyForm",
        "function followupDraft",
        "function returnDraft",
        "function notifications",
    ):
        assert marker in source
    for retired in ("supplier.html", "supplier.js", "index.html#/", "v12-workbench-entry"):
        assert retired not in source


def test_formal_h5_workbenches_do_not_claim_online_payment_or_silent_recording() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            Path("apps/h5/public/v12-workbench.js"),
            Path("apps/admin/public/h5/app.js"),
            Path("apps/call-h5/public/app.js"),
        )
    )

    for prohibited in ("微信支付", "支付宝支付", "自动录音", "原路退款"):
        assert prohibited not in sources
    assert "location.href = result.tel_url" in sources

from __future__ import annotations

from pathlib import Path

FORBIDDEN_API = "pkcs7_decrypt_"


def test_cryptography_fix_removes_temporary_waiver_and_keeps_affected_api_absent() -> None:
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    assert "cryptography==50.0.0" in requirements
    assert not Path("docs/quality/DEPENDENCY_RISK_ACCEPTANCE.md").exists()
    assert not Path("scripts/check_dependency_waiver.py").exists()
    assert "CVE-2026-69247" not in Path("security/waivers.json").read_text(encoding="utf-8")

    for workflow_path in Path(".github/workflows").glob("*.yml"):
        workflow = workflow_path.read_text(encoding="utf-8")
        assert "PYSEC-2026-3552" not in workflow
        assert "--ignore-vuln" not in workflow


def test_application_does_not_use_affected_pkcs7_decrypt_api() -> None:
    hits: list[str] = []
    for root in (Path("apps/api/src"), Path("scripts")):
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if FORBIDDEN_API in text:
                hits.append(path.as_posix())
    assert not hits, f"dependency waiver invalid: affected PKCS#7 decrypt API introduced in {hits}"

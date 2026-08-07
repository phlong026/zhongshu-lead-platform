from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts.check_dependency_waiver import WAIVER_EXPIRES_ON, validate_waiver

ADVISORY = "PYSEC-2026-3552"
FORBIDDEN_API = "pkcs7_decrypt_"


def test_temporary_cryptography_waiver_is_single_id_documented_and_ci_enforced() -> None:
    risk_doc = Path("docs/quality/DEPENDENCY_RISK_ACCEPTANCE.md").read_text(encoding="utf-8")
    assert ADVISORY in risk_doc
    assert WAIVER_EXPIRES_ON.isoformat() in risk_doc
    assert "cryptography 50.0.0" in risk_doc

    for workflow_path in (
        Path(".github/workflows/v12-pr-ci.yml"),
        Path(".github/workflows/v12-release-ci.yml"),
    ):
        workflow = workflow_path.read_text(encoding="utf-8")
        assert f"--ignore-vuln {ADVISORY}" in workflow
        assert workflow.count("--ignore-vuln") == 1
        assert "pip-audit" in workflow
        assert "python scripts/check_dependency_waiver.py" in workflow


def test_dependency_waiver_accepts_approved_deadline_but_fails_after_it() -> None:
    on_deadline = validate_waiver(date(2026, 8, 21))
    assert on_deadline["valid"] is True
    assert on_deadline["days_remaining"] == 0

    with pytest.raises(RuntimeError, match="expired on 2026-08-21"):
        validate_waiver(date(2026, 8, 22))


def test_application_does_not_use_affected_pkcs7_decrypt_api() -> None:
    hits: list[str] = []
    for root in (Path("apps/api/src"), Path("scripts")):
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if FORBIDDEN_API in text:
                hits.append(path.as_posix())
    assert not hits, f"dependency waiver invalid: affected PKCS#7 decrypt API introduced in {hits}"

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scripts.check_security_gate import Finding, Waiver, evaluate, load_waivers


def _semgrep(*results: dict) -> dict:
    return {"results": list(results), "errors": []}


def _trivy(*vulnerabilities: dict) -> dict:
    return {
        "Results": [
            {
                "Target": "zhongshu:test",
                "Vulnerabilities": list(vulnerabilities),
            }
        ]
    }


def test_clean_security_gate_passes() -> None:
    report = evaluate(semgrep_payload=_semgrep(), trivy_payload=_trivy(), waivers=[])
    assert report["blocking_count"] == 0
    assert report["waived_count"] == 0


def test_semgrep_error_is_blocking_but_warning_is_not() -> None:
    report = evaluate(
        semgrep_payload=_semgrep(
            {
                "check_id": "python.security.eval",
                "path": "apps/api/src/example.py",
                "extra": {"severity": "ERROR", "message": "unsafe eval"},
            },
            {
                "check_id": "python.style.warning",
                "path": "apps/api/src/example.py",
                "extra": {"severity": "WARNING", "message": "non-blocking review item"},
            },
        ),
        trivy_payload=_trivy(),
        waivers=[],
    )
    assert report["blocking_count"] == 1
    assert report["blocking_findings"][0]["id"] == "python.security.eval"


def test_trivy_high_and_critical_are_blocking() -> None:
    report = evaluate(
        semgrep_payload=_semgrep(),
        trivy_payload=_trivy(
            {
                "VulnerabilityID": "CVE-2099-0001",
                "Severity": "HIGH",
                "PkgName": "openssl",
                "InstalledVersion": "1.0",
                "FixedVersion": "1.1",
                "Title": "high test vulnerability",
            },
            {
                "VulnerabilityID": "CVE-2099-0002",
                "Severity": "CRITICAL",
                "PkgName": "libc",
                "InstalledVersion": "1.0",
                "FixedVersion": "1.2",
                "Title": "critical test vulnerability",
            },
            {
                "VulnerabilityID": "CVE-2099-0003",
                "Severity": "MEDIUM",
                "PkgName": "other",
                "InstalledVersion": "1.0",
                "FixedVersion": "1.1",
            },
        ),
        waivers=[],
    )
    assert report["blocking_count"] == 2
    assert {item["severity"] for item in report["blocking_findings"]} == {"HIGH", "CRITICAL"}


def test_waiver_requires_scanner_id_and_scope_match() -> None:
    finding = Finding(
        scanner="trivy",
        finding_id="CVE-2099-0100",
        severity="HIGH",
        scope="openssl",
        message="test",
    )
    exact = Waiver(
        scanner="trivy",
        finding_id="CVE-2099-0100",
        scope="openssl",
        reason="accepted temporarily",
        owner="security-owner",
        expires_on=date(2099, 12, 31),
    )
    wildcard = Waiver(
        scanner="trivy",
        finding_id="CVE-2099-0100",
        scope="*",
        reason="accepted temporarily",
        owner="security-owner",
        expires_on=date(2099, 12, 31),
    )
    wrong_scope = Waiver(
        scanner="trivy",
        finding_id="CVE-2099-0100",
        scope="libc",
        reason="wrong package",
        owner="security-owner",
        expires_on=date(2099, 12, 31),
    )
    wrong_scanner = Waiver(
        scanner="semgrep",
        finding_id="CVE-2099-0100",
        scope="openssl",
        reason="wrong scanner",
        owner="security-owner",
        expires_on=date(2099, 12, 31),
    )
    assert exact.matches(finding)
    assert wildcard.matches(finding)
    assert not wrong_scope.matches(finding)
    assert not wrong_scanner.matches(finding)


def test_matching_waiver_moves_finding_out_of_blockers() -> None:
    waiver = Waiver(
        scanner="trivy",
        finding_id="CVE-2099-0200",
        scope="openssl",
        reason="fixed image not available yet",
        owner="security-owner",
        expires_on=date(2099, 12, 31),
    )
    report = evaluate(
        semgrep_payload=_semgrep(),
        trivy_payload=_trivy(
            {
                "VulnerabilityID": "CVE-2099-0200",
                "Severity": "HIGH",
                "PkgName": "openssl",
                "InstalledVersion": "1.0",
                "FixedVersion": "1.1",
            }
        ),
        waivers=[waiver],
    )
    assert report["blocking_count"] == 0
    assert report["waived_count"] == 1
    assert report["waived_findings"][0]["owner"] == "security-owner"


def test_expired_waiver_registry_fails_even_if_finding_is_absent(tmp_path: Path) -> None:
    path = tmp_path / "waivers.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "waivers": [
                    {
                        "scanner": "trivy",
                        "id": "CVE-2099-0300",
                        "scope": "openssl",
                        "reason": "temporary only",
                        "owner": "security-owner",
                        "expires_on": "2026-08-08",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="expired security waiver"):
        load_waivers(path, today=date(2026, 8, 9))


def test_invalid_or_duplicate_waivers_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    missing.write_text(
        json.dumps({"version": 1, "waivers": [{"scanner": "trivy", "id": "CVE-X"}]}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="missing fields"):
        load_waivers(missing, today=date(2026, 8, 9))

    duplicate = tmp_path / "duplicate.json"
    item = {
        "scanner": "semgrep",
        "id": "python.security.rule",
        "scope": "*",
        "reason": "temporary",
        "owner": "security-owner",
        "expires_on": "2099-12-31",
    }
    duplicate.write_text(
        json.dumps({"version": 1, "waivers": [item, item]}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="duplicate security waiver"):
        load_waivers(duplicate, today=date(2026, 8, 9))


def test_semgrep_scan_errors_fail_closed() -> None:
    with pytest.raises(RuntimeError, match="semgrep reported scan errors"):
        evaluate(
            semgrep_payload={"results": [], "errors": [{"message": "registry unavailable"}]},
            trivy_payload=_trivy(),
            waivers=[],
        )

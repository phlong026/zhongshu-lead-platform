#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

BLOCKING_SEMGREP_SEVERITIES = {"ERROR"}
BLOCKING_TRIVY_SEVERITIES = {"HIGH", "CRITICAL"}
REQUIRED_WAIVER_FIELDS = {"scanner", "id", "scope", "reason", "owner", "expires_on"}
ALLOWED_SCANNERS = {"semgrep", "trivy"}


@dataclass(frozen=True)
class Finding:
    scanner: str
    finding_id: str
    severity: str
    scope: str
    message: str


@dataclass(frozen=True)
class Waiver:
    scanner: str
    finding_id: str
    scope: str
    reason: str
    owner: str
    expires_on: date

    def matches(self, finding: Finding) -> bool:
        if self.scanner != finding.scanner or self.finding_id != finding.finding_id:
            return False
        return self.scope == "*" or self.scope == finding.scope


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"required security evidence missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid security JSON evidence {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"security JSON root must be an object: {path}")
    return payload


def _read_exit_code(path: Path) -> int:
    if not path.is_file():
        raise RuntimeError(f"scanner exit-code evidence missing: {path}")
    raw = path.read_text(encoding="utf-8").strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"invalid scanner exit code in {path}: {raw!r}") from exc


def load_waivers(path: Path, *, today: date) -> list[Waiver]:
    payload = _read_json(path)
    if payload.get("version") != 1:
        raise RuntimeError("security waiver registry version must be 1")
    raw_waivers = payload.get("waivers")
    if not isinstance(raw_waivers, list):
        raise RuntimeError("security waiver registry 'waivers' must be a list")

    waivers: list[Waiver] = []
    seen: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(raw_waivers):
        if not isinstance(raw, dict):
            raise RuntimeError(f"security waiver #{index + 1} must be an object")
        missing = REQUIRED_WAIVER_FIELDS.difference(raw)
        if missing:
            raise RuntimeError(
                f"security waiver #{index + 1} missing fields: {', '.join(sorted(missing))}"
            )
        scanner = str(raw["scanner"]).strip().lower()
        finding_id = str(raw["id"]).strip()
        scope = str(raw["scope"]).strip()
        reason = str(raw["reason"]).strip()
        owner = str(raw["owner"]).strip()
        expires_raw = str(raw["expires_on"]).strip()
        if scanner not in ALLOWED_SCANNERS:
            raise RuntimeError(f"security waiver #{index + 1} has unsupported scanner: {scanner}")
        if not finding_id or not scope or not reason or not owner:
            raise RuntimeError(f"security waiver #{index + 1} contains an empty required value")
        try:
            expires_on = date.fromisoformat(expires_raw)
        except ValueError as exc:
            raise RuntimeError(
                f"security waiver #{index + 1} expires_on must be YYYY-MM-DD"
            ) from exc
        if expires_on < today:
            raise RuntimeError(
                f"expired security waiver: {scanner}/{finding_id}/{scope} expired {expires_on.isoformat()}"
            )
        key = (scanner, finding_id, scope)
        if key in seen:
            raise RuntimeError(f"duplicate security waiver: {scanner}/{finding_id}/{scope}")
        seen.add(key)
        waivers.append(
            Waiver(
                scanner=scanner,
                finding_id=finding_id,
                scope=scope,
                reason=reason,
                owner=owner,
                expires_on=expires_on,
            )
        )
    return waivers


def semgrep_findings(payload: dict[str, Any]) -> list[Finding]:
    errors = payload.get("errors") or []
    if errors:
        compact = json.dumps(errors[:5], ensure_ascii=False)
        raise RuntimeError(f"semgrep reported scan errors: {compact}")

    findings: list[Finding] = []
    for raw in payload.get("results") or []:
        if not isinstance(raw, dict):
            continue
        extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
        severity = str(extra.get("severity") or "").upper()
        if severity not in BLOCKING_SEMGREP_SEVERITIES:
            continue
        findings.append(
            Finding(
                scanner="semgrep",
                finding_id=str(raw.get("check_id") or "UNKNOWN_SEMGREP_RULE"),
                severity=severity,
                scope=str(raw.get("path") or "UNKNOWN_PATH"),
                message=str(extra.get("message") or "Semgrep security finding"),
            )
        )
    return findings


def trivy_findings(payload: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for result in payload.get("Results") or []:
        if not isinstance(result, dict):
            continue
        target = str(result.get("Target") or "UNKNOWN_TARGET")
        for raw in result.get("Vulnerabilities") or []:
            if not isinstance(raw, dict):
                continue
            severity = str(raw.get("Severity") or "").upper()
            if severity not in BLOCKING_TRIVY_SEVERITIES:
                continue
            package = str(raw.get("PkgName") or target)
            fixed = str(raw.get("FixedVersion") or "unfixed")
            title = str(raw.get("Title") or raw.get("Description") or "Trivy vulnerability")
            findings.append(
                Finding(
                    scanner="trivy",
                    finding_id=str(raw.get("VulnerabilityID") or "UNKNOWN_TRIVY_ID"),
                    severity=severity,
                    scope=package,
                    message=f"{title} (installed={raw.get('InstalledVersion')}, fixed={fixed})",
                )
            )
    return findings


def evaluate(
    *,
    semgrep_payload: dict[str, Any],
    trivy_payload: dict[str, Any],
    waivers: list[Waiver],
) -> dict[str, Any]:
    findings = semgrep_findings(semgrep_payload) + trivy_findings(trivy_payload)
    blockers: list[Finding] = []
    waived: list[tuple[Finding, Waiver]] = []
    for finding in findings:
        waiver = next((item for item in waivers if item.matches(finding)), None)
        if waiver is None:
            blockers.append(finding)
        else:
            waived.append((finding, waiver))

    return {
        "blocking_count": len(blockers),
        "waived_count": len(waived),
        "blocking_findings": [
            {
                "scanner": item.scanner,
                "id": item.finding_id,
                "severity": item.severity,
                "scope": item.scope,
                "message": item.message,
            }
            for item in blockers
        ],
        "waived_findings": [
            {
                "scanner": finding.scanner,
                "id": finding.finding_id,
                "severity": finding.severity,
                "scope": finding.scope,
                "owner": waiver.owner,
                "reason": waiver.reason,
                "expires_on": waiver.expires_on.isoformat(),
            }
            for finding, waiver in waived
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce V1.2 SAST and image vulnerability gates")
    parser.add_argument("--semgrep", default="dist/security/semgrep.json")
    parser.add_argument("--semgrep-exit", default="dist/security/semgrep-exit-code.txt")
    parser.add_argument("--trivy", default="dist/security/trivy-image.json")
    parser.add_argument("--trivy-exit", default="dist/security/trivy-exit-code.txt")
    parser.add_argument("--waivers", default="security/waivers.json")
    parser.add_argument("--output", default="dist/security/security-gate.json")
    parser.add_argument("--today", help="optional YYYY-MM-DD override for deterministic tests")
    args = parser.parse_args()

    current = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        semgrep_exit = _read_exit_code(Path(args.semgrep_exit))
        trivy_exit = _read_exit_code(Path(args.trivy_exit))
        if semgrep_exit != 0:
            raise RuntimeError(f"semgrep scanner failed with exit code {semgrep_exit}")
        if trivy_exit != 0:
            raise RuntimeError(f"trivy scanner/SBOM failed with exit code {trivy_exit}")

        waivers = load_waivers(Path(args.waivers), today=current)
        report = evaluate(
            semgrep_payload=_read_json(Path(args.semgrep)),
            trivy_payload=_read_json(Path(args.trivy)),
            waivers=waivers,
        )
        report.update(
            {
                "valid": report["blocking_count"] == 0,
                "checked_on": current.isoformat(),
                "semgrep_exit_code": semgrep_exit,
                "trivy_exit_code": trivy_exit,
                "active_waiver_count": len(waivers),
            }
        )
    except RuntimeError as exc:
        report = {
            "valid": False,
            "checked_on": current.isoformat(),
            "error": str(exc),
        }

    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

BLOCKING_SEMGREP_SEVERITIES = {"ERROR"}
BLOCKING_TRIVY_SEVERITIES = {"HIGH", "CRITICAL"}
REQUIRED_WAIVER_FIELDS = {
    "scanner",
    "id",
    "scope",
    "reason",
    "owner",
    "created_on",
    "expires_on",
}
ALLOWED_SCANNERS = {"semgrep", "trivy"}
MAX_WAIVER_LIFETIME_DAYS = 30
TRIVY_SBOM_VERSION = "0.70.0"
TRIVY_INPUT_ARTIFACT_NAME = "/tmp/app-image.tar"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


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
    created_on: date
    expires_on: date

    def matches(self, finding: Finding) -> bool:
        return (
            self.scanner == finding.scanner
            and self.finding_id == finding.finding_id
            and self.scope == finding.scope
        )


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


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"scanned image archive missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        if scanner not in ALLOWED_SCANNERS:
            raise RuntimeError(f"security waiver #{index + 1} has unsupported scanner: {scanner}")
        if not finding_id or not scope or not reason or not owner:
            raise RuntimeError(f"security waiver #{index + 1} contains an empty required value")
        if scope == "*":
            raise RuntimeError(
                f"security waiver #{index + 1} uses forbidden repository-wide scope '*'"
            )
        try:
            created_on = date.fromisoformat(str(raw["created_on"]).strip())
            expires_on = date.fromisoformat(str(raw["expires_on"]).strip())
        except ValueError as exc:
            raise RuntimeError(
                f"security waiver #{index + 1} created_on/expires_on must be YYYY-MM-DD"
            ) from exc
        if created_on > today:
            raise RuntimeError(
                f"security waiver #{index + 1} has future created_on {created_on.isoformat()}"
            )
        if expires_on < created_on:
            raise RuntimeError(f"security waiver #{index + 1} expires before it was created")
        lifetime = (expires_on - created_on).days
        if lifetime > MAX_WAIVER_LIFETIME_DAYS:
            raise RuntimeError(
                f"security waiver #{index + 1} lifetime {lifetime}d exceeds "
                f"{MAX_WAIVER_LIFETIME_DAYS}d maximum"
            )
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
                created_on=created_on,
                expires_on=expires_on,
            )
        )
    return waivers


def semgrep_findings(payload: dict[str, Any]) -> list[Finding]:
    if "results" not in payload or not isinstance(payload["results"], list):
        raise RuntimeError("semgrep report must contain a results array")
    if "errors" not in payload or not isinstance(payload["errors"], list):
        raise RuntimeError("semgrep report must contain an errors array")
    errors = payload["errors"]
    if errors:
        compact = json.dumps(errors[:5], ensure_ascii=False)
        raise RuntimeError(f"semgrep reported scan errors: {compact}")

    findings: list[Finding] = []
    for index, raw in enumerate(payload["results"]):
        if not isinstance(raw, dict):
            raise RuntimeError(f"semgrep result #{index + 1} must be an object")
        check_id = raw.get("check_id")
        path = raw.get("path")
        extra = raw.get("extra")
        if not isinstance(check_id, str) or not check_id.strip():
            raise RuntimeError(f"semgrep result #{index + 1} missing check_id")
        if not isinstance(path, str) or not path.strip():
            raise RuntimeError(f"semgrep result #{index + 1} missing path")
        if not isinstance(extra, dict):
            raise RuntimeError(f"semgrep result #{index + 1} missing extra object")
        severity_raw = extra.get("severity")
        if not isinstance(severity_raw, str) or not severity_raw.strip():
            raise RuntimeError(f"semgrep result #{index + 1} missing severity")
        severity = severity_raw.upper()
        if severity not in BLOCKING_SEMGREP_SEVERITIES:
            continue
        findings.append(
            Finding(
                scanner="semgrep",
                finding_id=check_id.strip(),
                severity=severity,
                scope=path.strip(),
                message=str(extra.get("message") or "Semgrep security finding"),
            )
        )
    return findings


def trivy_findings(
    payload: dict[str, Any],
    *,
    expected_artifact_name: str,
    expected_image_ref: str,
    expected_image_id: str,
) -> list[Finding]:
    if payload.get("SchemaVersion") != 2:
        raise RuntimeError("trivy report SchemaVersion must be 2")
    artifact_name = payload.get("ArtifactName")
    if artifact_name != expected_artifact_name:
        raise RuntimeError(
            f"trivy report artifact mismatch: expected {expected_artifact_name!r}, got {artifact_name!r}"
        )
    if payload.get("ArtifactType") != "container_image":
        raise RuntimeError("trivy report ArtifactType must be container_image")
    metadata = payload.get("Metadata")
    if not isinstance(metadata, dict):
        raise RuntimeError("trivy report Metadata must be an object")
    if metadata.get("ImageID") != expected_image_id:
        raise RuntimeError("trivy report Metadata.ImageID does not match scan subject")
    repo_tags = metadata.get("RepoTags")
    if not isinstance(repo_tags, list) or not all(isinstance(item, str) for item in repo_tags):
        raise RuntimeError("trivy report Metadata.RepoTags must be a string array")
    if expected_image_ref not in repo_tags:
        raise RuntimeError("trivy report Metadata.RepoTags does not contain scan subject image_ref")
    results = payload.get("Results")
    if not isinstance(results, list):
        raise RuntimeError("trivy report must contain a Results array")

    findings: list[Finding] = []
    for result_index, result in enumerate(results):
        if not isinstance(result, dict):
            raise RuntimeError(f"trivy result #{result_index + 1} must be an object")
        target = result.get("Target")
        if not isinstance(target, str) or not target.strip():
            raise RuntimeError(f"trivy result #{result_index + 1} missing Target")
        vulnerabilities = result.get("Vulnerabilities")
        if vulnerabilities is None:
            continue
        if not isinstance(vulnerabilities, list):
            raise RuntimeError(
                f"trivy result #{result_index + 1} Vulnerabilities must be null or an array"
            )
        for vuln_index, raw in enumerate(vulnerabilities):
            if not isinstance(raw, dict):
                raise RuntimeError(
                    f"trivy vulnerability #{result_index + 1}.{vuln_index + 1} must be an object"
                )
            finding_id = raw.get("VulnerabilityID")
            severity_raw = raw.get("Severity")
            package = raw.get("PkgName")
            if not isinstance(finding_id, str) or not finding_id.strip():
                raise RuntimeError(
                    f"trivy vulnerability #{result_index + 1}.{vuln_index + 1} missing VulnerabilityID"
                )
            if not isinstance(severity_raw, str) or not severity_raw.strip():
                raise RuntimeError(
                    f"trivy vulnerability #{result_index + 1}.{vuln_index + 1} missing Severity"
                )
            if not isinstance(package, str) or not package.strip():
                raise RuntimeError(
                    f"trivy vulnerability #{result_index + 1}.{vuln_index + 1} missing PkgName"
                )
            severity = severity_raw.upper()
            if severity not in BLOCKING_TRIVY_SEVERITIES:
                continue
            fixed = str(raw.get("FixedVersion") or "unfixed")
            title = str(raw.get("Title") or raw.get("Description") or "Trivy vulnerability")
            findings.append(
                Finding(
                    scanner="trivy",
                    finding_id=finding_id.strip(),
                    severity=severity,
                    scope=package.strip(),
                    message=f"{title} (installed={raw.get('InstalledVersion')}, fixed={fixed})",
                )
            )
    return findings


def _validate_docker_archive_identity(
    archive_path: Path,
    *,
    expected_image_ref: str,
    expected_image_id: str,
) -> None:
    expected_config = expected_image_id.removeprefix("sha256:") + ".json"
    try:
        with tarfile.open(archive_path, mode="r:*") as archive:
            manifest_member = archive.getmember("manifest.json")
            stream = archive.extractfile(manifest_member)
            if stream is None:
                raise RuntimeError("Docker archive manifest.json is unreadable")
            try:
                manifest = json.load(stream)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Docker archive manifest.json is invalid JSON: {exc}") from exc
            if not isinstance(manifest, list) or not manifest:
                raise RuntimeError("Docker archive manifest.json must be a non-empty array")
            matches = []
            for index, item in enumerate(manifest):
                if not isinstance(item, dict):
                    raise RuntimeError(f"Docker archive manifest entry #{index + 1} must be an object")
                repo_tags = item.get("RepoTags")
                if repo_tags is None:
                    continue
                if not isinstance(repo_tags, list) or not all(isinstance(tag, str) for tag in repo_tags):
                    raise RuntimeError(
                        f"Docker archive manifest entry #{index + 1} RepoTags must be a string array"
                    )
                if expected_image_ref in repo_tags:
                    matches.append(item)
            if len(matches) != 1:
                raise RuntimeError(
                    f"Docker archive must contain exactly one manifest entry for {expected_image_ref!r}"
                )
            config_name = matches[0].get("Config")
            if config_name != expected_config:
                raise RuntimeError(
                    f"Docker archive config mismatch: expected {expected_config!r}, got {config_name!r}"
                )
            archive.getmember(expected_config)
    except (tarfile.TarError, KeyError, OSError) as exc:
        raise RuntimeError(f"invalid Docker image archive: {exc}") from exc


def validate_scan_subject(payload: dict[str, Any], *, archive_path: Path) -> dict[str, str]:
    image_ref = payload.get("image_ref")
    image_id = payload.get("image_id")
    archive_sha256 = payload.get("archive_sha256")
    if not isinstance(image_ref, str) or not image_ref.strip():
        raise RuntimeError("scan subject missing image_ref")
    if not isinstance(image_id, str) or not _IMAGE_ID_RE.fullmatch(image_id):
        raise RuntimeError("scan subject image_id must be sha256:<64 lowercase hex>")
    if not isinstance(archive_sha256, str) or not _SHA256_RE.fullmatch(archive_sha256):
        raise RuntimeError("scan subject archive_sha256 must be a lowercase 64-char SHA-256")
    actual_archive_sha = _sha256_file(archive_path)
    if actual_archive_sha != archive_sha256:
        raise RuntimeError(
            f"scanned image archive SHA-256 mismatch: expected {archive_sha256}, got {actual_archive_sha}"
        )
    resolved_ref = image_ref.strip()
    resolved_id = image_id.strip()
    _validate_docker_archive_identity(
        archive_path,
        expected_image_ref=resolved_ref,
        expected_image_id=resolved_id,
    )
    return {
        "image_ref": resolved_ref,
        "image_id": resolved_id,
        "archive_sha256": archive_sha256,
        "trivy_artifact_name": TRIVY_INPUT_ARTIFACT_NAME,
    }


def _property_values(properties: list[Any]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for index, item in enumerate(properties):
        if not isinstance(item, dict):
            raise RuntimeError(f"SBOM component property #{index + 1} must be an object")
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise RuntimeError(f"SBOM component property #{index + 1} must contain string name/value")
        values.setdefault(name, []).append(value)
    return values


def _require_single_property(
    values: dict[str, list[str]],
    *,
    name: str,
    expected: str,
) -> None:
    actual = values.get(name)
    if actual != [expected]:
        raise RuntimeError(
            f"SBOM property {name} must contain exactly {expected!r}, got {actual!r}"
        )


def validate_sbom(
    payload: dict[str, Any],
    *,
    expected_artifact_name: str,
    expected_image_ref: str,
    expected_image_id: str,
) -> dict[str, Any]:
    if payload.get("bomFormat") != "CycloneDX":
        raise RuntimeError("SBOM bomFormat must be CycloneDX")
    spec_version = payload.get("specVersion")
    if not isinstance(spec_version, str) or not spec_version.strip():
        raise RuntimeError("SBOM specVersion must be present")
    components = payload.get("components")
    if not isinstance(components, list):
        raise RuntimeError("SBOM components must be an array")
    if not components:
        raise RuntimeError("SBOM components must not be empty")
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise RuntimeError("SBOM metadata must be an object")

    tools = metadata.get("tools")
    if not isinstance(tools, dict):
        raise RuntimeError("SBOM metadata.tools must be an object")
    tool_components = tools.get("components")
    if not isinstance(tool_components, list):
        raise RuntimeError("SBOM metadata.tools.components must be an array")
    trivy_tools = [
        item
        for item in tool_components
        if isinstance(item, dict)
        and item.get("group") == "aquasecurity"
        and item.get("name") == "trivy"
    ]
    if len(trivy_tools) != 1:
        raise RuntimeError("SBOM must identify exactly one Trivy generating tool")
    if trivy_tools[0].get("version") != TRIVY_SBOM_VERSION:
        raise RuntimeError(
            f"SBOM Trivy version mismatch: expected {TRIVY_SBOM_VERSION}, got {trivy_tools[0].get('version')!r}"
        )

    component = metadata.get("component")
    if not isinstance(component, dict):
        raise RuntimeError("SBOM metadata.component must be an object")
    if component.get("type") != "container":
        raise RuntimeError("SBOM metadata.component.type must be container")
    if component.get("name") != expected_artifact_name:
        raise RuntimeError(
            f"SBOM artifact name mismatch: expected {expected_artifact_name!r}, got {component.get('name')!r}"
        )
    properties = component.get("properties")
    if not isinstance(properties, list):
        raise RuntimeError("SBOM metadata.component.properties must be an array")
    property_values = _property_values(properties)
    _require_single_property(
        property_values,
        name="aquasecurity:trivy:Reference",
        expected=expected_image_ref,
    )
    _require_single_property(
        property_values,
        name="aquasecurity:trivy:RepoTag",
        expected=expected_image_ref,
    )
    _require_single_property(
        property_values,
        name="aquasecurity:trivy:ImageID",
        expected=expected_image_id,
    )
    return {
        "bom_format": "CycloneDX",
        "spec_version": spec_version,
        "component_count": len(components),
        "generator": f"trivy/{TRIVY_SBOM_VERSION}",
        "artifact_name": expected_artifact_name,
    }


def evaluate(
    *,
    semgrep_payload: dict[str, Any],
    trivy_payload: dict[str, Any],
    waivers: list[Waiver],
    expected_artifact_name: str,
    expected_image_ref: str,
    expected_image_id: str,
) -> dict[str, Any]:
    findings = semgrep_findings(semgrep_payload) + trivy_findings(
        trivy_payload,
        expected_artifact_name=expected_artifact_name,
        expected_image_ref=expected_image_ref,
        expected_image_id=expected_image_id,
    )
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
                "created_on": waiver.created_on.isoformat(),
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
    parser.add_argument("--sbom", default="dist/security/sbom.cdx.json")
    parser.add_argument("--subject", default="dist/security/scan-subject.json")
    parser.add_argument("--image-archive", default="dist/security/app-image.tar")
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

        subject = validate_scan_subject(
            _read_json(Path(args.subject)), archive_path=Path(args.image_archive)
        )
        sbom_summary = validate_sbom(
            _read_json(Path(args.sbom)),
            expected_artifact_name=subject["trivy_artifact_name"],
            expected_image_ref=subject["image_ref"],
            expected_image_id=subject["image_id"],
        )
        waivers = load_waivers(Path(args.waivers), today=current)
        report = evaluate(
            semgrep_payload=_read_json(Path(args.semgrep)),
            trivy_payload=_read_json(Path(args.trivy)),
            waivers=waivers,
            expected_artifact_name=subject["trivy_artifact_name"],
            expected_image_ref=subject["image_ref"],
            expected_image_id=subject["image_id"],
        )
        report.update(
            {
                "valid": report["blocking_count"] == 0,
                "checked_on": current.isoformat(),
                "semgrep_exit_code": semgrep_exit,
                "trivy_exit_code": trivy_exit,
                "active_waiver_count": len(waivers),
                "scan_subject": subject,
                "sbom": sbom_summary,
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

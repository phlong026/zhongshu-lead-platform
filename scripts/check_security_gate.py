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
    "occurrence",
    "reason",
    "owner",
    "created_on",
    "expires_on",
}
ALLOWED_SCANNERS = {"semgrep", "trivy"}
MAX_WAIVER_LIFETIME_DAYS = 30
SEMGREP_VERSION = "1.172.0"
SEMGREP_IMAGE_REF = "semgrep/semgrep@sha256:a8298d1c09c84b9a0bbc75ec915e37023fc4657360b6dbfa645261d2353a366c"
SEMGREP_RULES_COMMIT = "40b8c63f75dc7c22c8a77482d73bfb864b146f7e"
SEMGREP_RULES_TREE = "9b197569a9029ac2731667ef634f119dd61fb7dc"
SEMGREP_SOURCE_ROOTS = ("apps", "scripts", "migrations")
TRIVY_SBOM_VERSION = "0.70.0"
TRIVY_INPUT_ARTIFACT_NAME = "/tmp/app-image.tar"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_OCI_CONFIG_PATH_RE = re.compile(r"^blobs/sha256/([0-9a-f]{64})$")
_OCI_INDEX_MEDIA_TYPES = {
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.index.v1+json",
}
_OCI_MANIFEST_MEDIA_TYPES = {
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
}


@dataclass(frozen=True)
class Finding:
    scanner: str
    finding_id: str
    raw_id: str
    severity: str
    scope: str
    occurrence: str
    message: str


@dataclass(frozen=True)
class Waiver:
    scanner: str
    finding_id: str
    scope: str
    occurrence: str
    reason: str
    owner: str
    created_on: date
    expires_on: date

    def matches(self, finding: Finding) -> bool:
        return (
            self.scanner == finding.scanner
            and self.finding_id == finding.finding_id
            and self.scope == finding.scope
            and self.occurrence == finding.occurrence
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


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"required security evidence missing: {path}")
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"unable to read security evidence {path}: {exc}") from exc


def _read_exit_code(path: Path) -> int:
    raw = _read_text(path)
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
    seen: set[tuple[str, str, str, str]] = set()
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
        occurrence = str(raw["occurrence"]).strip()
        reason = str(raw["reason"]).strip()
        owner = str(raw["owner"]).strip()
        if scanner not in ALLOWED_SCANNERS:
            raise RuntimeError(f"security waiver #{index + 1} has unsupported scanner: {scanner}")
        if not finding_id or not scope or not occurrence or not reason or not owner:
            raise RuntimeError(f"security waiver #{index + 1} contains an empty required value")
        if scope == "*" or occurrence == "*":
            raise RuntimeError(
                f"security waiver #{index + 1} uses forbidden wildcard scope/occurrence"
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
                f"expired security waiver: {scanner}/{finding_id}/{scope}/{occurrence} "
                f"expired {expires_on.isoformat()}"
            )
        key = (scanner, finding_id, scope, occurrence)
        if key in seen:
            raise RuntimeError(
                f"duplicate security waiver: {scanner}/{finding_id}/{scope}/{occurrence}"
            )
        seen.add(key)
        waivers.append(
            Waiver(
                scanner=scanner,
                finding_id=finding_id,
                scope=scope,
                occurrence=occurrence,
                reason=reason,
                owner=owner,
                created_on=created_on,
                expires_on=expires_on,
            )
        )
    return waivers


def _expected_semgrep_paths(source_root: Path) -> set[str]:
    expected: set[str] = set()
    for root_name in SEMGREP_SOURCE_ROOTS:
        root = source_root / root_name
        if not root.is_dir():
            raise RuntimeError(f"Semgrep source root missing: {root_name}")
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".js"}:
                continue
            if any(part in {"__pycache__", "dist", "storage", ".git"} for part in path.parts):
                continue
            expected.add(path.relative_to(source_root).as_posix())
    if not expected:
        raise RuntimeError("Semgrep expected source inventory is empty")
    return expected


def validate_semgrep_identity_and_coverage(
    payload: dict[str, Any],
    *,
    source_root: Path,
    image_ref_path: Path,
    version_path: Path,
    rules_commit_path: Path,
    rules_tree_path: Path,
) -> dict[str, Any]:
    image_ref = _read_text(image_ref_path)
    if image_ref != SEMGREP_IMAGE_REF:
        raise RuntimeError(
            f"Semgrep image digest mismatch: expected {SEMGREP_IMAGE_REF!r}, got {image_ref!r}"
        )
    version = _read_text(version_path).splitlines()[0].strip()
    if version != SEMGREP_VERSION:
        raise RuntimeError(
            f"Semgrep version mismatch: expected {SEMGREP_VERSION}, got {version!r}"
        )
    rules_commit = _read_text(rules_commit_path)
    if rules_commit != SEMGREP_RULES_COMMIT:
        raise RuntimeError(
            f"Semgrep rules commit mismatch: expected {SEMGREP_RULES_COMMIT}, got {rules_commit!r}"
        )
    rules_tree = _read_text(rules_tree_path)
    if not _GIT_SHA_RE.fullmatch(rules_tree) or rules_tree != SEMGREP_RULES_TREE:
        raise RuntimeError(
            f"Semgrep rules tree mismatch: expected {SEMGREP_RULES_TREE}, got {rules_tree!r}"
        )
    if payload.get("version") != SEMGREP_VERSION:
        raise RuntimeError(
            f"Semgrep report version mismatch: expected {SEMGREP_VERSION}, got {payload.get('version')!r}"
        )
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        raise RuntimeError("Semgrep report paths must be an object")
    scanned = paths.get("scanned")
    if not isinstance(scanned, list) or not scanned:
        raise RuntimeError("Semgrep report paths.scanned must be a non-empty array")
    if not all(isinstance(item, str) and item.strip() for item in scanned):
        raise RuntimeError("Semgrep report paths.scanned must contain non-empty strings")
    if len(set(scanned)) != len(scanned):
        raise RuntimeError("Semgrep report paths.scanned contains duplicate paths")
    skipped_rules = payload.get("skipped_rules")
    if not isinstance(skipped_rules, list):
        raise RuntimeError("Semgrep report skipped_rules must be an array")
    if skipped_rules:
        raise RuntimeError("Semgrep skipped one or more configured rules")

    expected = _expected_semgrep_paths(source_root)
    scanned_set = {Path(item).as_posix() for item in scanned}
    missing = sorted(expected.difference(scanned_set))
    if missing:
        preview = ", ".join(missing[:20])
        suffix = "..." if len(missing) > 20 else ""
        raise RuntimeError(
            f"Semgrep scan coverage missing {len(missing)} Python/JavaScript files: {preview}{suffix}"
        )
    return {
        "version": version,
        "image_ref": image_ref,
        "rules_commit": rules_commit,
        "rules_tree": rules_tree,
        "expected_source_count": len(expected),
        "scanned_path_count": len(scanned_set),
    }


def _semgrep_occurrence(raw: dict[str, Any], *, index: int) -> str:
    start = raw.get("start")
    end = raw.get("end")
    if not isinstance(start, dict) or not isinstance(end, dict):
        raise RuntimeError(f"Semgrep blocking result #{index} missing start/end location")
    values = []
    for label, location in (("start", start), ("end", end)):
        line = location.get("line")
        col = location.get("col")
        if not isinstance(line, int) or line <= 0 or not isinstance(col, int) or col <= 0:
            raise RuntimeError(f"Semgrep blocking result #{index} has invalid {label} location")
        values.extend([line, col])
    return f"L{values[0]}:C{values[1]}-L{values[2]}:C{values[3]}"


def semgrep_findings(payload: dict[str, Any]) -> list[Finding]:
    if "results" not in payload or not isinstance(payload["results"], list):
        raise RuntimeError("Semgrep report must contain a results array")
    if "errors" not in payload or not isinstance(payload["errors"], list):
        raise RuntimeError("Semgrep report must contain an errors array")
    errors = payload["errors"]
    if errors:
        compact = json.dumps(errors[:5], ensure_ascii=False)
        raise RuntimeError(f"Semgrep reported scan errors: {compact}")

    findings: list[Finding] = []
    for index, raw in enumerate(payload["results"], start=1):
        if not isinstance(raw, dict):
            raise RuntimeError(f"Semgrep result #{index} must be an object")
        check_id = raw.get("check_id")
        path = raw.get("path")
        extra = raw.get("extra")
        if not isinstance(check_id, str) or not check_id.strip():
            raise RuntimeError(f"Semgrep result #{index} missing check_id")
        if not isinstance(path, str) or not path.strip():
            raise RuntimeError(f"Semgrep result #{index} missing path")
        if not isinstance(extra, dict):
            raise RuntimeError(f"Semgrep result #{index} missing extra object")
        severity_raw = extra.get("severity")
        if not isinstance(severity_raw, str) or not severity_raw.strip():
            raise RuntimeError(f"Semgrep result #{index} missing severity")
        severity = severity_raw.upper()
        if severity not in BLOCKING_SEMGREP_SEVERITIES:
            continue
        findings.append(
            Finding(
                scanner="semgrep",
                finding_id=check_id.strip().rsplit(".", 1)[-1],
                raw_id=check_id.strip(),
                severity=severity,
                scope=Path(path.strip()).as_posix(),
                occurrence=_semgrep_occurrence(raw, index=index),
                message=str(extra.get("message") or "Semgrep security finding"),
            )
        )
    return findings


def _validate_package_inventory(result: dict[str, Any], *, label: str) -> int:
    packages = result.get("Packages")
    if not isinstance(packages, list) or not packages:
        raise RuntimeError(f"Trivy {label} Packages must be a non-empty array")
    seen: set[tuple[str, str]] = set()
    for index, package in enumerate(packages, start=1):
        if not isinstance(package, dict):
            raise RuntimeError(f"Trivy {label} package #{index} must be an object")
        name = package.get("Name")
        version = package.get("Version")
        if not isinstance(name, str) or not name.strip():
            raise RuntimeError(f"Trivy {label} package #{index} missing Name")
        if not isinstance(version, str) or not version.strip():
            raise RuntimeError(f"Trivy {label} package #{index} missing Version")
        identity = (name.strip(), version.strip())
        if identity in seen:
            raise RuntimeError(f"Trivy {label} package inventory contains duplicate {identity!r}")
        seen.add(identity)
    return len(packages)


def _trivy_package_purls(payload: dict[str, Any]) -> set[str]:
    results = payload.get("Results")
    if not isinstance(results, list) or not results:
        raise RuntimeError("Trivy report Results must be a non-empty array")

    inventories: dict[tuple[str, str], set[str]] = {}
    expected_inventories = {
        ("os-pkgs", "debian"): "Debian OS",
        ("lang-pkgs", "python-pkg"): "Python",
    }
    for result in results:
        if not isinstance(result, dict):
            continue
        identity = (result.get("Class"), result.get("Type"))
        label = expected_inventories.get(identity)
        if label is None:
            continue
        if identity in inventories:
            raise RuntimeError(f"Trivy report contains multiple {label} package inventories")
        packages = result.get("Packages")
        if not isinstance(packages, list) or not packages:
            raise RuntimeError(f"Trivy {label} Packages must be a non-empty array")
        purls: set[str] = set()
        for index, package in enumerate(packages, start=1):
            if not isinstance(package, dict):
                raise RuntimeError(f"Trivy {label} package #{index} must be an object")
            identifier = package.get("Identifier")
            if not isinstance(identifier, dict):
                raise RuntimeError(f"Trivy {label} package #{index} missing Identifier")
            purl = identifier.get("PURL")
            if not isinstance(purl, str) or not purl.strip():
                raise RuntimeError(f"Trivy {label} package #{index} missing Identifier.PURL")
            normalized = purl.strip()
            if normalized in purls:
                raise RuntimeError(f"Trivy {label} package inventory contains duplicate PURL {normalized!r}")
            purls.add(normalized)
        inventories[identity] = purls

    missing = [label for identity, label in expected_inventories.items() if identity not in inventories]
    if missing:
        raise RuntimeError(f"Trivy report missing package PURL inventory: {', '.join(missing)}")
    combined = set().union(*inventories.values())
    if sum(len(items) for items in inventories.values()) != len(combined):
        raise RuntimeError("Trivy Debian and Python package inventories contain duplicate PURLs")
    return combined


def trivy_findings(
    payload: dict[str, Any],
    *,
    expected_artifact_name: str,
    expected_image_ref: str,
    expected_image_id: str,
) -> tuple[list[Finding], dict[str, int]]:
    if payload.get("SchemaVersion") != 2:
        raise RuntimeError("Trivy report SchemaVersion must be 2")
    artifact_name = payload.get("ArtifactName")
    if artifact_name != expected_artifact_name:
        raise RuntimeError(
            f"Trivy report artifact mismatch: expected {expected_artifact_name!r}, got {artifact_name!r}"
        )
    if payload.get("ArtifactType") != "container_image":
        raise RuntimeError("Trivy report ArtifactType must be container_image")
    metadata = payload.get("Metadata")
    if not isinstance(metadata, dict):
        raise RuntimeError("Trivy report Metadata must be an object")
    if metadata.get("ImageID") != expected_image_id:
        raise RuntimeError("Trivy report Metadata.ImageID does not match scan subject")
    repo_tags = metadata.get("RepoTags")
    if not isinstance(repo_tags, list) or not all(isinstance(item, str) for item in repo_tags):
        raise RuntimeError("Trivy report Metadata.RepoTags must be a string array")
    if expected_image_ref not in repo_tags:
        raise RuntimeError("Trivy report Metadata.RepoTags does not contain scan subject image_ref")
    results = payload.get("Results")
    if not isinstance(results, list) or not results:
        raise RuntimeError("Trivy report Results must be a non-empty array")

    findings: list[Finding] = []
    os_package_count: int | None = None
    python_package_count: int | None = None
    for result_index, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            raise RuntimeError(f"Trivy result #{result_index} must be an object")
        target = result.get("Target")
        result_class = result.get("Class")
        result_type = result.get("Type")
        if not isinstance(target, str) or not target.strip():
            raise RuntimeError(f"Trivy result #{result_index} missing Target")
        if not isinstance(result_class, str) or not result_class.strip():
            raise RuntimeError(f"Trivy result #{result_index} missing Class")
        if not isinstance(result_type, str) or not result_type.strip():
            raise RuntimeError(f"Trivy result #{result_index} missing Type")

        if result_class == "os-pkgs" and result_type == "debian":
            if os_package_count is not None:
                raise RuntimeError("Trivy report contains multiple Debian OS package inventories")
            os_package_count = _validate_package_inventory(result, label="Debian OS")
        if result_class == "lang-pkgs" and result_type == "python-pkg":
            if python_package_count is not None:
                raise RuntimeError("Trivy report contains multiple Python package inventories")
            python_package_count = _validate_package_inventory(result, label="Python")

        vulnerabilities = result.get("Vulnerabilities")
        if vulnerabilities is None:
            continue
        if not isinstance(vulnerabilities, list):
            raise RuntimeError(
                f"Trivy result #{result_index} Vulnerabilities must be null or an array"
            )
        for vuln_index, raw in enumerate(vulnerabilities, start=1):
            if not isinstance(raw, dict):
                raise RuntimeError(
                    f"Trivy vulnerability #{result_index}.{vuln_index} must be an object"
                )
            finding_id = raw.get("VulnerabilityID")
            severity_raw = raw.get("Severity")
            package = raw.get("PkgName")
            installed_version = raw.get("InstalledVersion")
            if not isinstance(finding_id, str) or not finding_id.strip():
                raise RuntimeError(
                    f"Trivy vulnerability #{result_index}.{vuln_index} missing VulnerabilityID"
                )
            if not isinstance(severity_raw, str) or not severity_raw.strip():
                raise RuntimeError(
                    f"Trivy vulnerability #{result_index}.{vuln_index} missing Severity"
                )
            if not isinstance(package, str) or not package.strip():
                raise RuntimeError(
                    f"Trivy vulnerability #{result_index}.{vuln_index} missing PkgName"
                )
            severity = severity_raw.upper()
            if severity not in BLOCKING_TRIVY_SEVERITIES:
                continue
            if not isinstance(installed_version, str) or not installed_version.strip():
                raise RuntimeError(
                    f"Trivy blocking vulnerability #{result_index}.{vuln_index} missing InstalledVersion"
                )
            fixed = str(raw.get("FixedVersion") or "unfixed")
            title = str(raw.get("Title") or raw.get("Description") or "Trivy vulnerability")
            occurrence = "|".join(
                [
                    target.strip(),
                    result_class.strip(),
                    result_type.strip(),
                    installed_version.strip(),
                ]
            )
            findings.append(
                Finding(
                    scanner="trivy",
                    finding_id=finding_id.strip(),
                    raw_id=finding_id.strip(),
                    severity=severity,
                    scope=package.strip(),
                    occurrence=occurrence,
                    message=f"{title} (installed={installed_version}, fixed={fixed})",
                )
            )

    if os_package_count is None:
        raise RuntimeError("Trivy report missing Debian OS package inventory")
    if python_package_count is None:
        raise RuntimeError("Trivy report missing Python package inventory")
    return findings, {
        "debian_package_count": os_package_count,
        "python_package_count": python_package_count,
    }


def _read_archive_member(archive: tarfile.TarFile, name: str) -> bytes:
    try:
        member = archive.getmember(name)
    except KeyError as exc:
        raise RuntimeError(f"Docker archive member missing: {name}") from exc
    if not member.isfile():
        raise RuntimeError(f"Docker archive member is not a regular file: {name}")
    stream = archive.extractfile(member)
    if stream is None:
        raise RuntimeError(f"Docker archive member is unreadable: {name}")
    return stream.read()


def _read_archive_json(archive: tarfile.TarFile, name: str) -> Any:
    try:
        return json.loads(_read_archive_member(archive, name))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Docker archive {name} is invalid JSON: {exc}") from exc


def _read_verified_oci_blob(
    archive: tarfile.TarFile,
    descriptor: Any,
    *,
    label: str,
) -> tuple[str, bytes]:
    if not isinstance(descriptor, dict):
        raise RuntimeError(f"{label} descriptor must be an object")
    digest = descriptor.get("digest")
    if not isinstance(digest, str) or not _IMAGE_ID_RE.fullmatch(digest):
        raise RuntimeError(f"{label} descriptor digest must be sha256:<64 lowercase hex>")
    size = descriptor.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise RuntimeError(f"{label} descriptor size must be a non-negative integer")
    raw = _read_archive_member(archive, f"blobs/sha256/{digest.removeprefix('sha256:')}")
    actual_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual_digest != digest:
        raise RuntimeError(f"{label} blob digest mismatch: expected {digest}, got {actual_digest}")
    if len(raw) != size:
        raise RuntimeError(f"{label} blob size mismatch: expected {size}, got {len(raw)}")
    return digest, raw


def _reachable_oci_config_digests(
    archive: tarfile.TarFile,
    descriptor: Any,
    *,
    label: str,
    depth: int = 0,
) -> set[str]:
    if depth > 4:
        raise RuntimeError("Docker OCI descriptor nesting exceeds four levels")
    if not isinstance(descriptor, dict):
        raise RuntimeError(f"{label} descriptor must be an object")
    media_type = descriptor.get("mediaType")
    if not isinstance(media_type, str):
        raise RuntimeError(f"{label} descriptor mediaType must be a string")
    _, raw = _read_verified_oci_blob(archive, descriptor, label=label)
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} blob is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 2:
        raise RuntimeError(f"{label} blob must be a schemaVersion 2 object")

    if media_type in _OCI_INDEX_MEDIA_TYPES:
        manifests = payload.get("manifests")
        if not isinstance(manifests, list) or not manifests:
            raise RuntimeError(f"{label} index manifests must be a non-empty array")
        configs: set[str] = set()
        for index, child in enumerate(manifests, start=1):
            configs.update(
                _reachable_oci_config_digests(
                    archive,
                    child,
                    label=f"{label} manifest #{index}",
                    depth=depth + 1,
                )
            )
        return configs

    if media_type in _OCI_MANIFEST_MEDIA_TYPES:
        config = payload.get("config")
        digest, _ = _read_verified_oci_blob(archive, config, label=f"{label} config")
        return {digest}

    raise RuntimeError(f"{label} uses unsupported OCI mediaType {media_type!r}")


def _validate_oci_archive_identity(
    archive: tarfile.TarFile,
    *,
    config_name: str,
    expected_image_id: str,
) -> str:
    config_match = _OCI_CONFIG_PATH_RE.fullmatch(config_name)
    if config_match is None:
        raise RuntimeError(f"Docker archive Config path is not a valid OCI SHA-256 blob: {config_name!r}")
    config_digest = "sha256:" + config_match.group(1)
    config_raw = _read_archive_member(archive, config_name)
    actual_config_digest = "sha256:" + hashlib.sha256(config_raw).hexdigest()
    if actual_config_digest != config_digest:
        raise RuntimeError(
            f"Docker archive OCI config digest mismatch: expected {config_digest}, "
            f"got {actual_config_digest}"
        )

    index = _read_archive_json(archive, "index.json")
    if not isinstance(index, dict) or index.get("schemaVersion") != 2:
        raise RuntimeError("Docker archive index.json must be a schemaVersion 2 object")
    manifests = index.get("manifests")
    if not isinstance(manifests, list) or not manifests:
        raise RuntimeError("Docker archive index.json manifests must be a non-empty array")
    matches = [item for item in manifests if isinstance(item, dict) and item.get("digest") == expected_image_id]
    if len(matches) != 1:
        # 不同 docker 存储后端导出的 OCI 布局里，index.json 记录的是 manifest 摘要，
        # 与 docker image inspect 返回的镜像 ID 摘要体系可能不同；退而用已经过
        # 内容哈希校验的配置摘要确认归档中恰好只有一个镜像与之对应。
        config_matches = []
        for item in manifests:
            if not isinstance(item, dict):
                continue
            try:
                reachable = _reachable_oci_config_digests(archive, item, label="Docker OCI image")
            except RuntimeError:
                continue
            if config_digest in reachable:
                config_matches.append(item)
        if len(config_matches) != 1:
            raise RuntimeError(
                f"Docker OCI index must contain exactly one descriptor for ImageID {expected_image_id!r}"
            )
        matches = config_matches
    reachable_configs = _reachable_oci_config_digests(
        archive,
        matches[0],
        label="Docker OCI image",
    )
    if config_digest not in reachable_configs:
        raise RuntimeError(
            f"Docker archive Config {config_digest!r} is not linked from ImageID {expected_image_id!r}"
        )
    return config_digest


def _validate_docker_archive_identity(
    archive_path: Path,
    *,
    expected_image_ref: str,
    expected_image_id: str,
) -> str:
    expected_config = expected_image_id.removeprefix("sha256:") + ".json"
    try:
        with tarfile.open(archive_path, mode="r:*") as archive:
            manifest = _read_archive_json(archive, "manifest.json")
            if not isinstance(manifest, list) or not manifest:
                raise RuntimeError("Docker archive manifest.json must be a non-empty array")
            matches = []
            for index, item in enumerate(manifest, start=1):
                if not isinstance(item, dict):
                    raise RuntimeError(f"Docker archive manifest entry #{index} must be an object")
                repo_tags = item.get("RepoTags")
                if repo_tags is None:
                    continue
                if not isinstance(repo_tags, list) or not all(isinstance(tag, str) for tag in repo_tags):
                    raise RuntimeError(
                        f"Docker archive manifest entry #{index} RepoTags must be a string array"
                    )
                if expected_image_ref in repo_tags:
                    matches.append(item)
            if len(matches) != 1:
                raise RuntimeError(
                    f"Docker archive must contain exactly one manifest entry for {expected_image_ref!r}"
                )
            config_name = matches[0].get("Config")
            if config_name == expected_config:
                config_raw = _read_archive_member(archive, expected_config)
                actual_config = hashlib.sha256(config_raw).hexdigest() + ".json"
                if actual_config != expected_config:
                    raise RuntimeError(
                        f"Docker archive config content mismatch: expected {expected_config!r}, "
                        f"got {actual_config!r}"
                    )
                return expected_image_id
            elif isinstance(config_name, str) and _OCI_CONFIG_PATH_RE.fullmatch(config_name):
                return _validate_oci_archive_identity(
                    archive,
                    config_name=config_name,
                    expected_image_id=expected_image_id,
                )
            else:
                raise RuntimeError(
                    f"Docker archive config mismatch: expected legacy {expected_config!r} "
                    f"or an OCI config blob, got {config_name!r}"
                )
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
    trivy_image_id = _validate_docker_archive_identity(
        archive_path,
        expected_image_ref=resolved_ref,
        expected_image_id=resolved_id,
    )
    return {
        "image_ref": resolved_ref,
        "image_id": resolved_id,
        "trivy_image_id": trivy_image_id,
        "archive_sha256": archive_sha256,
        "trivy_artifact_name": TRIVY_INPUT_ARTIFACT_NAME,
    }


def _property_values(properties: list[Any]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for index, item in enumerate(properties, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(f"SBOM component property #{index} must be an object")
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise RuntimeError(f"SBOM component property #{index} must contain string name/value")
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
    expected_package_purls: set[str],
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
            f"SBOM Trivy version mismatch: expected {TRIVY_SBOM_VERSION}, "
            f"got {trivy_tools[0].get('version')!r}"
        )

    root_component = metadata.get("component")
    if not isinstance(root_component, dict):
        raise RuntimeError("SBOM metadata.component must be an object")
    root_ref = root_component.get("bom-ref")
    if not isinstance(root_ref, str) or not root_ref.strip():
        raise RuntimeError("SBOM metadata.component.bom-ref must be present")
    if root_component.get("type") != "container":
        raise RuntimeError("SBOM metadata.component.type must be container")
    if root_component.get("name") != expected_artifact_name:
        raise RuntimeError(
            f"SBOM artifact name mismatch: expected {expected_artifact_name!r}, "
            f"got {root_component.get('name')!r}"
        )
    properties = root_component.get("properties")
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

    component_refs: set[str] = set()
    component_types: set[str] = set()
    component_purls: set[str] = set()
    for index, component in enumerate(components, start=1):
        if not isinstance(component, dict):
            raise RuntimeError(f"SBOM component #{index} must be an object")
        bom_ref = component.get("bom-ref")
        component_type = component.get("type")
        name = component.get("name")
        version = component.get("version")
        for field_name, value in (
            ("bom-ref", bom_ref),
            ("type", component_type),
            ("name", name),
            ("version", version),
        ):
            if not isinstance(value, str) or not value.strip():
                raise RuntimeError(f"SBOM component #{index} missing {field_name}")
        if bom_ref in component_refs:
            raise RuntimeError(f"SBOM contains duplicate component bom-ref {bom_ref!r}")
        component_refs.add(bom_ref)
        component_types.add(component_type)
        purl = component.get("purl")
        if component_type == "library":
            if not isinstance(purl, str) or not purl.strip():
                raise RuntimeError(f"SBOM library component #{index} missing purl")
            normalized_purl = purl.strip()
            if normalized_purl in component_purls:
                raise RuntimeError(f"SBOM contains duplicate component purl {normalized_purl!r}")
            component_purls.add(normalized_purl)
    if "operating-system" not in component_types:
        raise RuntimeError("SBOM missing operating-system component")
    if "library" not in component_types:
        raise RuntimeError("SBOM missing library components")
    missing_packages = sorted(expected_package_purls.difference(component_purls))
    unexpected_packages = sorted(component_purls.difference(expected_package_purls))
    if missing_packages or unexpected_packages:
        details = []
        if missing_packages:
            details.append(f"missing={missing_packages[:10]!r}")
        if unexpected_packages:
            details.append(f"unexpected={unexpected_packages[:10]!r}")
        raise RuntimeError("SBOM package inventory mismatch: " + "; ".join(details))

    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        raise RuntimeError("SBOM dependencies must be a non-empty array")
    allowed_refs = component_refs | {root_ref}
    dependency_refs: set[str] = set()
    for index, dependency in enumerate(dependencies, start=1):
        if not isinstance(dependency, dict):
            raise RuntimeError(f"SBOM dependency #{index} must be an object")
        ref = dependency.get("ref")
        depends_on = dependency.get("dependsOn")
        if not isinstance(ref, str) or not ref.strip():
            raise RuntimeError(f"SBOM dependency #{index} missing ref")
        if ref not in allowed_refs:
            raise RuntimeError(f"SBOM dependency #{index} references unknown ref {ref!r}")
        if ref in dependency_refs:
            raise RuntimeError(f"SBOM contains duplicate dependency ref {ref!r}")
        dependency_refs.add(ref)
        if not isinstance(depends_on, list) or not all(
            isinstance(item, str) and item.strip() for item in depends_on
        ):
            raise RuntimeError(f"SBOM dependency #{index} dependsOn must be a string array")
        unknown = sorted(set(depends_on).difference(component_refs))
        if unknown:
            raise RuntimeError(
                f"SBOM dependency #{index} dependsOn contains unknown refs: {', '.join(unknown[:10])}"
            )
    if root_ref not in dependency_refs:
        raise RuntimeError("SBOM dependency graph missing root container dependency entry")

    return {
        "bom_format": "CycloneDX",
        "spec_version": spec_version,
        "component_count": len(components),
        "dependency_count": len(dependencies),
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
) -> tuple[dict[str, Any], dict[str, int]]:
    trivy_items, trivy_inventory = trivy_findings(
        trivy_payload,
        expected_artifact_name=expected_artifact_name,
        expected_image_ref=expected_image_ref,
        expected_image_id=expected_image_id,
    )
    findings = semgrep_findings(semgrep_payload) + trivy_items
    blockers: list[Finding] = []
    waived: list[tuple[Finding, Waiver]] = []
    for finding in findings:
        waiver = next((item for item in waivers if item.matches(finding)), None)
        if waiver is None:
            blockers.append(finding)
        else:
            waived.append((finding, waiver))

    report = {
        "blocking_count": len(blockers),
        "waived_count": len(waived),
        "blocking_findings": [
            {
                "scanner": item.scanner,
                "id": item.finding_id,
                "raw_id": item.raw_id,
                "severity": item.severity,
                "scope": item.scope,
                "occurrence": item.occurrence,
                "message": item.message,
            }
            for item in blockers
        ],
        "waived_findings": [
            {
                "scanner": finding.scanner,
                "id": finding.finding_id,
                "raw_id": finding.raw_id,
                "severity": finding.severity,
                "scope": finding.scope,
                "occurrence": finding.occurrence,
                "owner": waiver.owner,
                "reason": waiver.reason,
                "created_on": waiver.created_on.isoformat(),
                "expires_on": waiver.expires_on.isoformat(),
            }
            for finding, waiver in waived
        ],
    }
    return report, trivy_inventory


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce V1.2 SAST and image vulnerability gates")
    parser.add_argument("--semgrep", default="dist/security/semgrep.json")
    parser.add_argument("--semgrep-exit", default="dist/security/semgrep-exit-code.txt")
    parser.add_argument("--semgrep-image-ref", default="dist/security/semgrep-image-ref.txt")
    parser.add_argument("--semgrep-version", default="dist/security/semgrep-version.txt")
    parser.add_argument("--semgrep-rules-commit", default="dist/security/semgrep-rules-commit.txt")
    parser.add_argument("--semgrep-rules-tree", default="dist/security/semgrep-rules-tree.txt")
    parser.add_argument("--source-root", default=".")
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
            raise RuntimeError(f"Semgrep scanner failed with exit code {semgrep_exit}")
        if trivy_exit != 0:
            raise RuntimeError(f"Trivy scanner/SBOM failed with exit code {trivy_exit}")

        semgrep_payload = _read_json(Path(args.semgrep))
        semgrep_summary = validate_semgrep_identity_and_coverage(
            semgrep_payload,
            source_root=Path(args.source_root).resolve(),
            image_ref_path=Path(args.semgrep_image_ref),
            version_path=Path(args.semgrep_version),
            rules_commit_path=Path(args.semgrep_rules_commit),
            rules_tree_path=Path(args.semgrep_rules_tree),
        )
        subject = validate_scan_subject(
            _read_json(Path(args.subject)), archive_path=Path(args.image_archive)
        )
        trivy_payload = _read_json(Path(args.trivy))
        expected_package_purls = _trivy_package_purls(trivy_payload)
        sbom_summary = validate_sbom(
            _read_json(Path(args.sbom)),
            expected_artifact_name=subject["trivy_artifact_name"],
            expected_image_ref=subject["image_ref"],
            expected_image_id=subject["trivy_image_id"],
            expected_package_purls=expected_package_purls,
        )
        waivers = load_waivers(Path(args.waivers), today=current)
        report, trivy_inventory = evaluate(
            semgrep_payload=semgrep_payload,
            trivy_payload=trivy_payload,
            waivers=waivers,
            expected_artifact_name=subject["trivy_artifact_name"],
            expected_image_ref=subject["image_ref"],
            expected_image_id=subject["trivy_image_id"],
        )
        report.update(
            {
                "valid": report["blocking_count"] == 0,
                "checked_on": current.isoformat(),
                "semgrep_exit_code": semgrep_exit,
                "trivy_exit_code": trivy_exit,
                "active_waiver_count": len(waivers),
                "semgrep": semgrep_summary,
                "scan_subject": subject,
                "trivy_inventory": trivy_inventory,
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

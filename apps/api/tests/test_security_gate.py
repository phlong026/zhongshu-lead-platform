from __future__ import annotations

import hashlib
import io
import json
import tarfile
from datetime import date
from pathlib import Path

import pytest

from scripts.check_security_gate import (
    SEMGREP_IMAGE_REF,
    SEMGREP_RULES_COMMIT,
    SEMGREP_RULES_TREE,
    SEMGREP_VERSION,
    TRIVY_INPUT_ARTIFACT_NAME,
    Finding,
    Waiver,
    evaluate,
    load_waivers,
    semgrep_findings,
    trivy_findings,
    validate_sbom,
    validate_scan_subject,
    validate_semgrep_identity_and_coverage,
)

IMAGE_REF = "zhongshu-security:test"
IMAGE_ID = "sha256:" + "1" * 64
CONFIG_NAME = "1" * 64 + ".json"
SEMGREP_OCCURRENCE = "L164:C33-L164:C40"
TRIVY_OCCURRENCE = "Python|lang-pkgs|python-pkg|49.0.0"


def _semgrep(*results: dict, scanned: list[str] | None = None) -> dict:
    return {
        "version": SEMGREP_VERSION,
        "results": list(results),
        "errors": [],
        "paths": {"scanned": scanned or ["apps/example.py"]},
        "skipped_rules": [],
    }


def _semgrep_error(
    *,
    check_id: str = "python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args",
    path: str = "scripts/verify_production.py",
    start_line: int = 164,
    start_col: int = 33,
    end_line: int = 164,
    end_col: int = 40,
) -> dict:
    return {
        "check_id": check_id,
        "path": path,
        "start": {"line": start_line, "col": start_col},
        "end": {"line": end_line, "col": end_col},
        "extra": {"severity": "ERROR", "message": "test finding"},
    }


def _trivy(*vulnerabilities: dict) -> dict:
    return {
        "SchemaVersion": 2,
        "ArtifactName": TRIVY_INPUT_ARTIFACT_NAME,
        "ArtifactType": "container_image",
        "Metadata": {
            "ImageID": IMAGE_ID,
            "RepoTags": [IMAGE_REF],
        },
        "Results": [
            {
                "Target": "bookworm (debian 12)",
                "Class": "os-pkgs",
                "Type": "debian",
                "Packages": [
                    {"Name": "base-files", "Version": "12.4"},
                    {"Name": "libc6", "Version": "2.36"},
                ],
                "Vulnerabilities": [],
            },
            {
                "Target": "Python",
                "Class": "lang-pkgs",
                "Type": "python-pkg",
                "Packages": [
                    {"Name": "cryptography", "Version": "49.0.0"},
                    {"Name": "fastapi", "Version": "0.141.1"},
                ],
                "Vulnerabilities": list(vulnerabilities),
            },
        ],
    }


def _waiver(**overrides) -> Waiver:
    values = {
        "scanner": "trivy",
        "finding_id": "CVE-2099-0100",
        "scope": "openssl",
        "occurrence": "Python|lang-pkgs|python-pkg|1.0.0",
        "reason": "accepted temporarily",
        "owner": "security-owner",
        "created_on": date(2026, 8, 9),
        "expires_on": date(2026, 9, 8),
    }
    values.update(overrides)
    return Waiver(**values)


def _sbom() -> dict:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "components": [
            {
                "bom-ref": "os-ref",
                "type": "operating-system",
                "name": "debian",
                "version": "12",
            },
            {
                "bom-ref": "lib-ref",
                "type": "library",
                "name": "fastapi",
                "version": "0.141.1",
            },
        ],
        "dependencies": [
            {"ref": "root-ref", "dependsOn": ["os-ref", "lib-ref"]},
            {"ref": "os-ref", "dependsOn": []},
            {"ref": "lib-ref", "dependsOn": []},
        ],
        "metadata": {
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "group": "aquasecurity",
                        "name": "trivy",
                        "version": "0.70.0",
                    }
                ]
            },
            "component": {
                "bom-ref": "root-ref",
                "type": "container",
                "name": TRIVY_INPUT_ARTIFACT_NAME,
                "properties": [
                    {"name": "aquasecurity:trivy:Reference", "value": IMAGE_REF},
                    {"name": "aquasecurity:trivy:RepoTag", "value": IMAGE_REF},
                    {"name": "aquasecurity:trivy:ImageID", "value": IMAGE_ID},
                ],
            },
        },
    }


def _evaluate(*, semgrep: dict | None = None, trivy: dict | None = None, waivers=None):
    return evaluate(
        semgrep_payload=semgrep or _semgrep(),
        trivy_payload=trivy or _trivy(),
        waivers=list(waivers or []),
        expected_artifact_name=TRIVY_INPUT_ARTIFACT_NAME,
        expected_image_ref=IMAGE_REF,
        expected_image_id=IMAGE_ID,
    )


def _add_tar_bytes(archive: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(payload)
    archive.addfile(info, io.BytesIO(payload))


def _write_image_archive(
    path: Path,
    *,
    image_ref: str = IMAGE_REF,
    config_name: str = CONFIG_NAME,
) -> str:
    manifest = [{"Config": config_name, "RepoTags": [image_ref], "Layers": []}]
    with tarfile.open(path, "w") as archive:
        _add_tar_bytes(archive, "manifest.json", json.dumps(manifest).encode("utf-8"))
        _add_tar_bytes(archive, config_name, b"{}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_semgrep_identity(root: Path) -> dict[str, Path]:
    paths = {
        "image_ref": root / "semgrep-image-ref.txt",
        "version": root / "semgrep-version.txt",
        "rules_commit": root / "semgrep-rules-commit.txt",
        "rules_tree": root / "semgrep-rules-tree.txt",
    }
    paths["image_ref"].write_text(SEMGREP_IMAGE_REF + "\n", encoding="utf-8")
    paths["version"].write_text(SEMGREP_VERSION + "\n", encoding="utf-8")
    paths["rules_commit"].write_text(SEMGREP_RULES_COMMIT + "\n", encoding="utf-8")
    paths["rules_tree"].write_text(SEMGREP_RULES_TREE + "\n", encoding="utf-8")
    return paths


def test_clean_security_gate_passes_with_required_inventories() -> None:
    report, inventory = _evaluate()
    assert report["blocking_count"] == 0
    assert report["waived_count"] == 0
    assert inventory == {"debian_package_count": 2, "python_package_count": 2}


def test_semgrep_error_is_blocking_but_warning_is_not() -> None:
    report, _ = _evaluate(
        semgrep=_semgrep(
            _semgrep_error(),
            {
                "check_id": "python.style.warning",
                "path": "apps/example.py",
                "extra": {"severity": "WARNING", "message": "non-blocking review item"},
            },
        )
    )
    assert report["blocking_count"] == 1
    finding = report["blocking_findings"][0]
    assert finding["id"] == "dangerous-subprocess-use-tainted-env-args"
    assert finding["occurrence"] == SEMGREP_OCCURRENCE


def test_semgrep_identity_and_complete_source_coverage(tmp_path: Path) -> None:
    for directory in ("apps", "scripts", "migrations"):
        (tmp_path / directory).mkdir()
    (tmp_path / "apps" / "a.py").write_text("print('a')\n", encoding="utf-8")
    (tmp_path / "scripts" / "b.js").write_text("console.log('b');\n", encoding="utf-8")
    (tmp_path / "migrations" / "c.py").write_text("x = 1\n", encoding="utf-8")
    identity = _write_semgrep_identity(tmp_path)
    payload = _semgrep(
        scanned=["apps/a.py", "scripts/b.js", "migrations/c.py"]
    )
    summary = validate_semgrep_identity_and_coverage(
        payload,
        source_root=tmp_path,
        image_ref_path=identity["image_ref"],
        version_path=identity["version"],
        rules_commit_path=identity["rules_commit"],
        rules_tree_path=identity["rules_tree"],
    )
    assert summary["expected_source_count"] == 3
    assert summary["scanned_path_count"] == 3

    payload["paths"]["scanned"].remove("scripts/b.js")
    with pytest.raises(RuntimeError, match="scan coverage missing 1"):
        validate_semgrep_identity_and_coverage(
            payload,
            source_root=tmp_path,
            image_ref_path=identity["image_ref"],
            version_path=identity["version"],
            rules_commit_path=identity["rules_commit"],
            rules_tree_path=identity["rules_tree"],
        )


def test_semgrep_empty_scan_or_wrong_identity_fails_closed(tmp_path: Path) -> None:
    for directory in ("apps", "scripts", "migrations"):
        (tmp_path / directory).mkdir()
    (tmp_path / "apps" / "a.py").write_text("x = 1\n", encoding="utf-8")
    identity = _write_semgrep_identity(tmp_path)
    payload = _semgrep(scanned=[])
    payload["paths"]["scanned"] = []
    with pytest.raises(RuntimeError, match="paths.scanned must be a non-empty array"):
        validate_semgrep_identity_and_coverage(
            payload,
            source_root=tmp_path,
            image_ref_path=identity["image_ref"],
            version_path=identity["version"],
            rules_commit_path=identity["rules_commit"],
            rules_tree_path=identity["rules_tree"],
        )

    identity["rules_tree"].write_text("0" * 40 + "\n", encoding="utf-8")
    payload["paths"]["scanned"] = ["apps/a.py"]
    with pytest.raises(RuntimeError, match="rules tree mismatch"):
        validate_semgrep_identity_and_coverage(
            payload,
            source_root=tmp_path,
            image_ref_path=identity["image_ref"],
            version_path=identity["version"],
            rules_commit_path=identity["rules_commit"],
            rules_tree_path=identity["rules_tree"],
        )


def test_trivy_high_and_critical_are_blocking_and_occurrence_bound() -> None:
    report, _ = _evaluate(
        trivy=_trivy(
            {
                "VulnerabilityID": "CVE-2099-0001",
                "Severity": "HIGH",
                "PkgName": "cryptography",
                "InstalledVersion": "49.0.0",
                "FixedVersion": "50.0.0",
                "Title": "high test vulnerability",
            },
            {
                "VulnerabilityID": "CVE-2099-0002",
                "Severity": "CRITICAL",
                "PkgName": "fastapi",
                "InstalledVersion": "0.141.1",
                "FixedVersion": "0.142.0",
                "Title": "critical test vulnerability",
            },
        )
    )
    assert report["blocking_count"] == 2
    first = report["blocking_findings"][0]
    assert first["occurrence"] == TRIVY_OCCURRENCE


def test_trivy_empty_or_missing_expected_inventory_fails_closed() -> None:
    kwargs = {
        "expected_artifact_name": TRIVY_INPUT_ARTIFACT_NAME,
        "expected_image_ref": IMAGE_REF,
        "expected_image_id": IMAGE_ID,
    }
    payload = _trivy()
    payload["Results"] = []
    with pytest.raises(RuntimeError, match="Results must be a non-empty array"):
        trivy_findings(payload, **kwargs)

    payload = _trivy()
    payload["Results"] = [payload["Results"][1]]
    with pytest.raises(RuntimeError, match="missing Debian OS package inventory"):
        trivy_findings(payload, **kwargs)

    payload = _trivy()
    payload["Results"] = [payload["Results"][0]]
    with pytest.raises(RuntimeError, match="missing Python package inventory"):
        trivy_findings(payload, **kwargs)

    payload = _trivy()
    payload["Results"][0]["Packages"] = []
    with pytest.raises(RuntimeError, match="Debian OS Packages must be a non-empty array"):
        trivy_findings(payload, **kwargs)


def test_waiver_requires_exact_occurrence_not_only_id_and_scope() -> None:
    finding = Finding(
        scanner="trivy",
        finding_id="CVE-2099-0100",
        raw_id="CVE-2099-0100",
        severity="HIGH",
        scope="openssl",
        occurrence="Python|lang-pkgs|python-pkg|1.0.0",
        message="test",
    )
    exact = _waiver()
    wrong_scope = _waiver(scope="libc")
    wrong_occurrence = _waiver(occurrence="Python|lang-pkgs|python-pkg|1.0.1")
    assert exact.matches(finding)
    assert not wrong_scope.matches(finding)
    assert not wrong_occurrence.matches(finding)


def test_matching_waiver_only_suppresses_one_semgrep_occurrence() -> None:
    first = _semgrep_error(start_line=164, start_col=33, end_line=164, end_col=40)
    second = _semgrep_error(start_line=200, start_col=10, end_line=200, end_col=20)
    waiver = Waiver(
        scanner="semgrep",
        finding_id="dangerous-subprocess-use-tainted-env-args",
        scope="scripts/verify_production.py",
        occurrence=SEMGREP_OCCURRENCE,
        reason="exact reviewed occurrence",
        owner="security-owner",
        created_on=date(2026, 8, 9),
        expires_on=date(2026, 9, 8),
    )
    report, _ = _evaluate(
        semgrep=_semgrep(first, second, scanned=["scripts/verify_production.py"]),
        waivers=[waiver],
    )
    assert report["waived_count"] == 1
    assert report["blocking_count"] == 1
    assert report["blocking_findings"][0]["occurrence"] == "L200:C10-L200:C20"


def _write_waivers(path: Path, waivers: list[dict]) -> None:
    path.write_text(json.dumps({"version": 1, "waivers": waivers}), encoding="utf-8")


def _waiver_json(**overrides) -> dict:
    value = {
        "scanner": "trivy",
        "id": "CVE-2099-0300",
        "scope": "openssl",
        "occurrence": "Python|lang-pkgs|python-pkg|1.0.0",
        "reason": "temporary only",
        "owner": "security-owner",
        "created_on": "2026-08-09",
        "expires_on": "2026-09-08",
    }
    value.update(overrides)
    return value


def test_expired_waiver_registry_fails_even_if_finding_is_absent(tmp_path: Path) -> None:
    path = tmp_path / "waivers.json"
    _write_waivers(
        path,
        [_waiver_json(created_on="2026-08-01", expires_on="2026-08-08")],
    )
    with pytest.raises(RuntimeError, match="expired security waiver"):
        load_waivers(path, today=date(2026, 8, 9))


def test_wildcard_future_or_long_lived_waivers_fail_closed(tmp_path: Path) -> None:
    wildcard = tmp_path / "wildcard.json"
    _write_waivers(wildcard, [_waiver_json(scope="*")])
    with pytest.raises(RuntimeError, match="forbidden wildcard"):
        load_waivers(wildcard, today=date(2026, 8, 9))

    wildcard_occurrence = tmp_path / "wildcard-occurrence.json"
    _write_waivers(wildcard_occurrence, [_waiver_json(occurrence="*")])
    with pytest.raises(RuntimeError, match="forbidden wildcard"):
        load_waivers(wildcard_occurrence, today=date(2026, 8, 9))

    future = tmp_path / "future.json"
    _write_waivers(
        future,
        [_waiver_json(created_on="2026-08-10", expires_on="2026-08-20")],
    )
    with pytest.raises(RuntimeError, match="future created_on"):
        load_waivers(future, today=date(2026, 8, 9))

    long_lived = tmp_path / "long-lived.json"
    _write_waivers(
        long_lived,
        [_waiver_json(created_on="2026-08-01", expires_on="2026-09-15")],
    )
    with pytest.raises(RuntimeError, match="exceeds 30d maximum"):
        load_waivers(long_lived, today=date(2026, 8, 9))


def test_invalid_or_duplicate_waivers_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    _write_waivers(missing, [{"scanner": "trivy", "id": "CVE-X"}])
    with pytest.raises(RuntimeError, match="missing fields"):
        load_waivers(missing, today=date(2026, 8, 9))

    duplicate = tmp_path / "duplicate.json"
    item = _waiver_json()
    _write_waivers(duplicate, [item, item])
    with pytest.raises(RuntimeError, match="duplicate security waiver"):
        load_waivers(duplicate, today=date(2026, 8, 9))


def test_semgrep_scan_errors_and_schema_damage_fail_closed() -> None:
    with pytest.raises(RuntimeError, match="Semgrep reported scan errors"):
        semgrep_findings({"results": [], "errors": [{"message": "registry unavailable"}]})
    with pytest.raises(RuntimeError, match="results array"):
        semgrep_findings({"errors": []})
    with pytest.raises(RuntimeError, match="errors array"):
        semgrep_findings({"results": []})
    with pytest.raises(RuntimeError, match="missing severity"):
        semgrep_findings(
            {
                "results": [
                    {
                        "check_id": "broken",
                        "path": "example.py",
                        "extra": {},
                    }
                ],
                "errors": [],
            }
        )
    with pytest.raises(RuntimeError, match="missing start/end location"):
        semgrep_findings(
            {
                "results": [
                    {
                        "check_id": "security.rule",
                        "path": "example.py",
                        "extra": {"severity": "ERROR"},
                    }
                ],
                "errors": [],
            }
        )


def test_trivy_schema_damage_or_subject_mismatch_fail_closed() -> None:
    kwargs = {
        "expected_artifact_name": TRIVY_INPUT_ARTIFACT_NAME,
        "expected_image_ref": IMAGE_REF,
        "expected_image_id": IMAGE_ID,
    }
    with pytest.raises(RuntimeError, match="SchemaVersion"):
        trivy_findings({}, **kwargs)
    with pytest.raises(RuntimeError, match="artifact mismatch"):
        payload = _trivy()
        payload["ArtifactName"] = "other.tar"
        trivy_findings(payload, **kwargs)
    with pytest.raises(RuntimeError, match="ImageID"):
        payload = _trivy()
        payload["Metadata"]["ImageID"] = "sha256:" + "2" * 64
        trivy_findings(payload, **kwargs)
    with pytest.raises(RuntimeError, match="RepoTags"):
        payload = _trivy()
        payload["Metadata"]["RepoTags"] = ["other:image"]
        trivy_findings(payload, **kwargs)
    with pytest.raises(RuntimeError, match="Vulnerabilities must be null or an array"):
        payload = _trivy()
        payload["Results"][0]["Vulnerabilities"] = {}
        trivy_findings(payload, **kwargs)


def test_scan_subject_binds_hash_manifest_tag_and_config(tmp_path: Path) -> None:
    archive = tmp_path / "app-image.tar"
    digest = _write_image_archive(archive)
    subject = validate_scan_subject(
        {"image_ref": IMAGE_REF, "image_id": IMAGE_ID, "archive_sha256": digest},
        archive_path=archive,
    )
    assert subject["archive_sha256"] == digest
    assert subject["trivy_artifact_name"] == TRIVY_INPUT_ARTIFACT_NAME

    archive.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="archive SHA-256 mismatch"):
        validate_scan_subject(
            {"image_ref": IMAGE_REF, "image_id": IMAGE_ID, "archive_sha256": digest},
            archive_path=archive,
        )


def test_scan_subject_rejects_wrong_archive_tag_or_config(tmp_path: Path) -> None:
    wrong_tag = tmp_path / "wrong-tag.tar"
    wrong_tag_digest = _write_image_archive(wrong_tag, image_ref="other:image")
    with pytest.raises(RuntimeError, match="exactly one manifest entry"):
        validate_scan_subject(
            {"image_ref": IMAGE_REF, "image_id": IMAGE_ID, "archive_sha256": wrong_tag_digest},
            archive_path=wrong_tag,
        )

    wrong_config = tmp_path / "wrong-config.tar"
    wrong_config_digest = _write_image_archive(wrong_config, config_name="2" * 64 + ".json")
    with pytest.raises(RuntimeError, match="config mismatch"):
        validate_scan_subject(
            {"image_ref": IMAGE_REF, "image_id": IMAGE_ID, "archive_sha256": wrong_config_digest},
            archive_path=wrong_config,
        )


def test_scan_subject_requires_full_sha256_image_id(tmp_path: Path) -> None:
    archive = tmp_path / "app-image.tar"
    digest = _write_image_archive(archive)
    for bad_image_id in ("sha256:short", "sha256:" + "G" * 64, "not-a-sha256"):
        with pytest.raises(RuntimeError, match="image_id must be sha256"):
            validate_scan_subject(
                {"image_ref": IMAGE_REF, "image_id": bad_image_id, "archive_sha256": digest},
                archive_path=archive,
            )


def test_sbom_must_be_substantive_cyclonedx_with_valid_dependency_graph() -> None:
    sbom = _sbom()
    kwargs = {
        "expected_artifact_name": TRIVY_INPUT_ARTIFACT_NAME,
        "expected_image_ref": IMAGE_REF,
        "expected_image_id": IMAGE_ID,
    }
    summary = validate_sbom(sbom, **kwargs)
    assert summary["component_count"] == 2
    assert summary["dependency_count"] == 3
    assert summary["generator"] == "trivy/0.70.0"

    for bad_component in (None, {}):
        damaged = json.loads(json.dumps(sbom))
        damaged["components"] = [bad_component]
        with pytest.raises(RuntimeError, match="SBOM component #1"):
            validate_sbom(damaged, **kwargs)

    duplicate = json.loads(json.dumps(sbom))
    duplicate["components"][1]["bom-ref"] = duplicate["components"][0]["bom-ref"]
    with pytest.raises(RuntimeError, match="duplicate component bom-ref"):
        validate_sbom(duplicate, **kwargs)

    no_os = json.loads(json.dumps(sbom))
    no_os["components"] = [no_os["components"][1]]
    no_os["dependencies"] = [
        {"ref": "root-ref", "dependsOn": ["lib-ref"]},
        {"ref": "lib-ref", "dependsOn": []},
    ]
    with pytest.raises(RuntimeError, match="missing operating-system"):
        validate_sbom(no_os, **kwargs)

    unknown_dependency = json.loads(json.dumps(sbom))
    unknown_dependency["dependencies"][0]["dependsOn"].append("unknown-ref")
    with pytest.raises(RuntimeError, match="unknown refs"):
        validate_sbom(unknown_dependency, **kwargs)


def test_sbom_identity_and_generator_damage_fail_closed() -> None:
    sbom = _sbom()
    kwargs = {
        "expected_artifact_name": TRIVY_INPUT_ARTIFACT_NAME,
        "expected_image_ref": IMAGE_REF,
        "expected_image_id": IMAGE_ID,
    }
    wrong_tool_version = json.loads(json.dumps(sbom))
    wrong_tool_version["metadata"]["tools"]["components"][0]["version"] = "0.69.0"
    with pytest.raises(RuntimeError, match="Trivy version mismatch"):
        validate_sbom(wrong_tool_version, **kwargs)

    duplicate_reference = json.loads(json.dumps(sbom))
    duplicate_reference["metadata"]["component"]["properties"].append(
        {"name": "aquasecurity:trivy:Reference", "value": IMAGE_REF}
    )
    with pytest.raises(RuntimeError, match="must contain exactly"):
        validate_sbom(duplicate_reference, **kwargs)

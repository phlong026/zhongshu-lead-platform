from __future__ import annotations

import hashlib
import io
import json
import tarfile
from datetime import date
from pathlib import Path

import pytest

from scripts.check_security_gate import (
    TRIVY_INPUT_ARTIFACT_NAME,
    Finding,
    Waiver,
    evaluate,
    load_waivers,
    semgrep_findings,
    trivy_findings,
    validate_sbom,
    validate_scan_subject,
)

IMAGE_REF = "zhongshu-security:test"
IMAGE_ID = "sha256:" + "1" * 64
CONFIG_NAME = "1" * 64 + ".json"


def _semgrep(*results: dict) -> dict:
    return {"version": "1.172.0", "results": list(results), "errors": []}


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
                "Target": "debian",
                "Vulnerabilities": list(vulnerabilities),
            }
        ],
    }


def _waiver(**overrides) -> Waiver:
    values = {
        "scanner": "trivy",
        "finding_id": "CVE-2099-0100",
        "scope": "openssl",
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
                "type": "library",
                "name": "example-runtime-package",
                "version": "1.0.0",
            }
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


def _evaluate(*, semgrep: dict | None = None, trivy: dict | None = None, waivers=None) -> dict:
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
    manifest = [
        {
            "Config": config_name,
            "RepoTags": [image_ref],
            "Layers": [],
        }
    ]
    with tarfile.open(path, "w") as archive:
        _add_tar_bytes(archive, "manifest.json", json.dumps(manifest).encode("utf-8"))
        _add_tar_bytes(archive, config_name, b"{}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_clean_security_gate_passes() -> None:
    report = _evaluate()
    assert report["blocking_count"] == 0
    assert report["waived_count"] == 0


def test_semgrep_error_is_blocking_but_warning_is_not() -> None:
    report = _evaluate(
        semgrep=_semgrep(
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
        )
    )
    assert report["blocking_count"] == 1
    assert report["blocking_findings"][0]["id"] == "python.security.eval"


def test_trivy_high_and_critical_are_blocking() -> None:
    report = _evaluate(
        trivy=_trivy(
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
        )
    )
    assert report["blocking_count"] == 2
    assert {item["severity"] for item in report["blocking_findings"]} == {"HIGH", "CRITICAL"}


def test_waiver_requires_exact_scanner_id_and_scope_match() -> None:
    finding = Finding(
        scanner="trivy",
        finding_id="CVE-2099-0100",
        severity="HIGH",
        scope="openssl",
        message="test",
    )
    exact = _waiver()
    wrong_scope = _waiver(scope="libc")
    wrong_scanner = _waiver(scanner="semgrep")
    assert exact.matches(finding)
    assert not wrong_scope.matches(finding)
    assert not wrong_scanner.matches(finding)


def test_matching_waiver_moves_finding_out_of_blockers() -> None:
    waiver = _waiver(finding_id="CVE-2099-0200")
    report = _evaluate(
        trivy=_trivy(
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


def _write_waivers(path: Path, waivers: list[dict]) -> None:
    path.write_text(json.dumps({"version": 1, "waivers": waivers}), encoding="utf-8")


def _waiver_json(**overrides) -> dict:
    value = {
        "scanner": "trivy",
        "id": "CVE-2099-0300",
        "scope": "openssl",
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
    with pytest.raises(RuntimeError, match="forbidden repository-wide scope"):
        load_waivers(wildcard, today=date(2026, 8, 9))

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
    with pytest.raises(RuntimeError, match="semgrep reported scan errors"):
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
        {
            "image_ref": IMAGE_REF,
            "image_id": IMAGE_ID,
            "archive_sha256": digest,
        },
        archive_path=archive,
    )
    assert subject["archive_sha256"] == digest
    assert subject["trivy_artifact_name"] == TRIVY_INPUT_ARTIFACT_NAME

    archive.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="archive SHA-256 mismatch"):
        validate_scan_subject(
            {
                "image_ref": IMAGE_REF,
                "image_id": IMAGE_ID,
                "archive_sha256": digest,
            },
            archive_path=archive,
        )


def test_scan_subject_rejects_wrong_archive_tag_or_config(tmp_path: Path) -> None:
    wrong_tag = tmp_path / "wrong-tag.tar"
    wrong_tag_digest = _write_image_archive(wrong_tag, image_ref="other:image")
    with pytest.raises(RuntimeError, match="exactly one manifest entry"):
        validate_scan_subject(
            {
                "image_ref": IMAGE_REF,
                "image_id": IMAGE_ID,
                "archive_sha256": wrong_tag_digest,
            },
            archive_path=wrong_tag,
        )

    wrong_config = tmp_path / "wrong-config.tar"
    wrong_config_digest = _write_image_archive(
        wrong_config,
        config_name="2" * 64 + ".json",
    )
    with pytest.raises(RuntimeError, match="config mismatch"):
        validate_scan_subject(
            {
                "image_ref": IMAGE_REF,
                "image_id": IMAGE_ID,
                "archive_sha256": wrong_config_digest,
            },
            archive_path=wrong_config,
        )


def test_scan_subject_requires_full_sha256_image_id(tmp_path: Path) -> None:
    archive = tmp_path / "app-image.tar"
    digest = _write_image_archive(archive)
    for bad_image_id in ("sha256:short", "sha256:" + "G" * 64, "not-a-sha256"):
        with pytest.raises(RuntimeError, match="image_id must be sha256"):
            validate_scan_subject(
                {
                    "image_ref": IMAGE_REF,
                    "image_id": bad_image_id,
                    "archive_sha256": digest,
                },
                archive_path=archive,
            )


def test_sbom_must_be_substantive_cyclonedx_bound_to_archive_and_image() -> None:
    sbom = _sbom()
    kwargs = {
        "expected_artifact_name": TRIVY_INPUT_ARTIFACT_NAME,
        "expected_image_ref": IMAGE_REF,
        "expected_image_id": IMAGE_ID,
    }
    summary = validate_sbom(sbom, **kwargs)
    assert summary["bom_format"] == "CycloneDX"
    assert summary["component_count"] == 1
    assert summary["generator"] == "trivy/0.70.0"
    assert summary["artifact_name"] == TRIVY_INPUT_ARTIFACT_NAME

    damaged = json.loads(json.dumps(sbom))
    damaged["components"] = None
    with pytest.raises(RuntimeError, match="components must be an array"):
        validate_sbom(damaged, **kwargs)

    empty = json.loads(json.dumps(sbom))
    empty["components"] = []
    with pytest.raises(RuntimeError, match="components must not be empty"):
        validate_sbom(empty, **kwargs)

    missing_tools = json.loads(json.dumps(sbom))
    del missing_tools["metadata"]["tools"]
    with pytest.raises(RuntimeError, match="metadata.tools must be an object"):
        validate_sbom(missing_tools, **kwargs)

    wrong_tool_version = json.loads(json.dumps(sbom))
    wrong_tool_version["metadata"]["tools"]["components"][0]["version"] = "0.69.0"
    with pytest.raises(RuntimeError, match="Trivy version mismatch"):
        validate_sbom(wrong_tool_version, **kwargs)

    wrong_artifact = json.loads(json.dumps(sbom))
    wrong_artifact["metadata"]["component"]["name"] = "other.tar"
    with pytest.raises(RuntimeError, match="artifact name mismatch"):
        validate_sbom(wrong_artifact, **kwargs)

    duplicate_reference = json.loads(json.dumps(sbom))
    duplicate_reference["metadata"]["component"]["properties"].append(
        {"name": "aquasecurity:trivy:Reference", "value": IMAGE_REF}
    )
    with pytest.raises(RuntimeError, match="must contain exactly"):
        validate_sbom(duplicate_reference, **kwargs)

    wrong_repo_tag = json.loads(json.dumps(sbom))
    for item in wrong_repo_tag["metadata"]["component"]["properties"]:
        if item["name"] == "aquasecurity:trivy:RepoTag":
            item["value"] = "other:image"
    with pytest.raises(RuntimeError, match="RepoTag"):
        validate_sbom(wrong_repo_tag, **kwargs)

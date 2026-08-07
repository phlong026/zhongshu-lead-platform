from __future__ import annotations

import json
import zipfile

from scripts.package_release import (
    REQUIRED_RELEASE_DOCS,
    _copy_release_docs,
    _delivery_doc_name,
    build_source_zip,
    validate_release_docs,
)


def test_source_archive_contains_generated_v12_manifest_and_openapi(tmp_path) -> None:
    archive_path = tmp_path / "v12-source.zip"
    manifest = build_source_zip(archive_path, version="V1.2.0-test", dirty=False)

    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        manifest_names = [name for name in names if name.endswith("/RELEASE_MANIFEST.json")]
        history_names = [name for name in names if name.endswith("/GIT_HISTORY.txt")]
        openapi_names = [name for name in names if name.endswith("/docs/api/openapi.json")]
        assert len(names) == len(set(names))
        assert len(manifest_names) == 1
        assert len(history_names) == 1
        assert len(openapi_names) == 1
        payload = json.loads(archive.read(manifest_names[0]).decode("utf-8"))
        openapi = json.loads(archive.read(openapi_names[0]).decode("utf-8"))

    assert payload["release"] == "V1.2.0-test"
    assert payload["commit"] == manifest["commit"]
    assert payload["branch"] == manifest["branch"]
    assert "PostgreSQL 16 historical migration, semantic reconciliation and constraints" in payload["quality_gates"]
    assert "Comprehensive code/security review with no unresolved P0/P1/P2" in payload["quality_gates"]
    assert openapi["info"]["version"] == "1.2.0"
    assert "/api/v1/v1.2/reports/overview" in openapi["paths"]


def test_required_v12_delivery_documents_and_generated_openapi_exist(tmp_path) -> None:
    sources = validate_release_docs()
    assert len(sources) == len(REQUIRED_RELEASE_DOCS)
    assert "docs/quality/SECURITY_AUDIT.md" in REQUIRED_RELEASE_DOCS
    assert "docs/quality/DEPENDENCY_RISK_ACCEPTANCE.md" in REQUIRED_RELEASE_DOCS
    assert "docs/reviews/INDEX_V1.2.md" in REQUIRED_RELEASE_DOCS
    assert "docs/reviews/53-v1.2-sprint6-comprehensive-final-review.md" in REQUIRED_RELEASE_DOCS
    assert "docs/runbooks/DEPLOYMENT.md" in REQUIRED_RELEASE_DOCS
    assert "docs/runbooks/BACKUP_RESTORE.md" in REQUIRED_RELEASE_DOCS
    assert "docs/runbooks/V1.2_POST_LAUNCH.md" in REQUIRED_RELEASE_DOCS

    delivery_names = [_delivery_doc_name(source) for source in sources]
    assert len(delivery_names) == len(set(delivery_names))

    target = tmp_path / "quality"
    _copy_release_docs(target)
    copied = sorted(path.name for path in target.iterdir())
    expected = sorted([*delivery_names, "docs__api__openapi.json"])
    assert copied == expected
    openapi = json.loads((target / "docs__api__openapi.json").read_text(encoding="utf-8"))
    assert openapi["info"]["version"] == "1.2.0"
    assert any("SECURITY_AUDIT.md" in name for name in copied)
    assert any("DEPENDENCY_RISK_ACCEPTANCE.md" in name for name in copied)
    assert any("INDEX_V1.2.md" in name for name in copied)
    assert any("53-v1.2-sprint6-comprehensive-final-review.md" in name for name in copied)

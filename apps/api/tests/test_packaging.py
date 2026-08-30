from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.package_release import ROOT, package_release, tracked_files

pytestmark = pytest.mark.skipif(
    not (ROOT / ".git").exists(),
    reason="release packaging checks require a Git checkout; source archives intentionally omit .git",
)


def test_tracked_source_policy_excludes_runtime_private_and_generated_openapi_files():
    names = {path.as_posix() for path in tracked_files()}
    assert "README.md" in names
    assert "docs/api/openapi.json" not in names
    assert not any(name == ".env" or name.endswith((".db", ".sqlite", ".sqlite3", ".pyc")) for name in names)
    assert not any(name.startswith("storage/") or "/__pycache__/" in name for name in names)


def test_release_package_contains_generated_openapi_source_history_and_quality_docs(tmp_path: Path):
    artifacts = package_release(tmp_path, version="TEST-P0", allow_dirty=True)
    for path in artifacts.values():
        assert path.is_file() and path.stat().st_size > 0

    with zipfile.ZipFile(artifacts["source"]) as archive:
        names = set(archive.namelist())
        assert any(name.endswith("/README.md") for name in names)
        assert any(name.endswith("/RELEASE_MANIFEST.json") for name in names)
        assert any(name.endswith("/GIT_HISTORY.txt") for name in names)
        openapi_name = next(name for name in names if name.endswith("/docs/api/openapi.json"))
        openapi = json.loads(archive.read(openapi_name).decode("utf-8"))
        assert openapi["info"]["version"] == "1.2.2"
        assert "/api/v1/v1.2/reports/overview" in openapi["paths"]
        assert not any(name.endswith(("/.env", ".db", ".sqlite3", ".pyc")) for name in names)

    with zipfile.ZipFile(artifacts["delivery"]) as archive:
        names = set(archive.namelist())
        assert artifacts["source"].name in names
        assert artifacts["bundle"].name in names
        assert "交付说明.md" in names
        assert "SHA256SUMS.txt" in names
        assert "质量与发布资料/docs__api__openapi.json" in names
        assert "质量与发布资料/docs__quality__TEST_REPORT.md" in names
        assert "质量与发布资料/docs__quality__SECURITY_AUDIT.md" in names
        assert "质量与发布资料/docs__runbooks__V1.2_GO_NO_GO.md" in names

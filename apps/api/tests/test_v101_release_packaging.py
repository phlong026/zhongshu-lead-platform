from __future__ import annotations

import json
import zipfile
from pathlib import Path

from scripts.package_v101 import DEFAULT_VERSION, PROHIBITED_PATTERNS, package_release


def test_v101_packaging_policy_blocks_runtime_secrets_and_auto_dispatch_claims():
    assert DEFAULT_VERSION == "V1.0.1"
    samples = [
        ".env",
        "storage/evidence/audio.m4a",
        "backups/postgres/prod.dump",
        "infra/certs/privkey.pem",
        "runtime.sqlite3",
    ]
    for sample in samples:
        assert any(pattern.search(sample) for pattern in PROHIBITED_PATTERNS), sample


def test_v101_release_package_contains_source_bundle_manifest_and_quality_docs(tmp_path):
    quality = tmp_path / "quality"
    quality.mkdir()
    (quality / "pytest.txt").write_text("tests passed\n", encoding="utf-8")
    artifacts = package_release(tmp_path / "release", version="V1.0.1", quality_dir=quality, allow_dirty=True)

    assert all(path.is_file() and path.stat().st_size > 0 for path in artifacts.values())
    with zipfile.ZipFile(artifacts["source"]) as archive:
        names = archive.namelist()
        manifest_name = next(name for name in names if name.endswith("/RELEASE_MANIFEST.json"))
        manifest = json.loads(archive.read(manifest_name).decode("utf-8"))
        assert manifest["release"] == "V1.0.1"
        assert "Automatic, rotation or weighted dispatch" in manifest["excluded_scope"]
        assert not any("/backups/postgres/" in name or name.endswith("privkey.pem") for name in names)

    with zipfile.ZipFile(artifacts["delivery"]) as archive:
        names = archive.namelist()
        assert any(name.endswith("完整源码.zip") for name in names)
        assert any(name.endswith("完整Git提交历史.bundle") for name in names)
        assert "SHA256SUMS.txt" in names
        assert "质量与发布资料/RELEASE_NOTES_V1.0.1.md" in names
        assert "质量与发布资料/INDEX_V1.0.1.md" in names
        assert "质量与发布资料/自动检查/pytest.txt" in names

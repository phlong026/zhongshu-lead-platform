from __future__ import annotations

import json
import zipfile

from scripts.package_release import build_source_zip


def test_source_archive_contains_one_generated_v12_manifest(tmp_path) -> None:
    archive_path = tmp_path / "v12-source.zip"
    manifest = build_source_zip(archive_path, version="V1.2.0-test", dirty=False)

    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        manifest_names = [name for name in names if name.endswith("/RELEASE_MANIFEST.json")]
        history_names = [name for name in names if name.endswith("/GIT_HISTORY.txt")]
        assert len(names) == len(set(names))
        assert len(manifest_names) == 1
        assert len(history_names) == 1
        payload = json.loads(archive.read(manifest_names[0]).decode("utf-8"))

    assert payload["release"] == "V1.2.0-test"
    assert payload["commit"] == manifest["commit"]
    assert payload["branch"] == manifest["branch"]
    assert "PostgreSQL 16 historical migration and reconciliation" in payload["quality_gates"]

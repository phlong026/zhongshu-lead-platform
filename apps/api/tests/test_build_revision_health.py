from __future__ import annotations

from pathlib import Path

import apps.api.src.main as main_module


def test_runtime_build_sha_prefers_baked_marker(tmp_path, monkeypatch) -> None:
    marker = tmp_path / ".build-sha"
    marker.write_text("A" * 40 + "\n", encoding="utf-8")
    monkeypatch.setattr(main_module, "ROOT", tmp_path)
    monkeypatch.setenv("APP_BUILD_SHA", "b" * 40)

    assert main_module._runtime_build_sha() == "a" * 40


def test_runtime_build_sha_falls_back_to_environment_without_marker(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main_module, "ROOT", tmp_path)
    monkeypatch.setenv("APP_BUILD_SHA", "C" * 40)

    assert main_module._runtime_build_sha() == "c" * 40


def test_dockerfile_bakes_build_sha_marker() -> None:
    root = Path(__file__).resolve().parents[3]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")

    assert "ARG APP_BUILD_SHA=unknown" in dockerfile
    assert "org.opencontainers.image.revision=\"${APP_BUILD_SHA}\"" in dockerfile
    assert "/app/.build-sha" in dockerfile

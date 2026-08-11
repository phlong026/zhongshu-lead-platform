from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.preflight_v12 import (
    _compose_python_command,
    _database_url_from_postgres,
    _redact,
    _sensitive_values,
)
from scripts.validate_production_env import derive_compose_database_url
from scripts.verify_production import image_tag, inspect_image_metadata, load_scan_subject_image_id


def test_production_compose_requires_reviewed_image_and_disables_implicit_migration() -> None:
    prod_compose = Path("docker-compose.prod.yml").read_text(encoding="utf-8")
    base_compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    entrypoint = Path("docker/entrypoint.sh").read_text(encoding="utf-8")
    scheduler_entrypoint = Path("docker/scheduler-entrypoint.sh").read_text(encoding="utf-8")
    prepare_env = Path("docker/prepare-env.sh").read_text(encoding="utf-8")
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "APP_IMAGE must reference the reviewed V1.2 image" in prod_compose
    assert 'RUN_DB_MIGRATIONS: "false"' in prod_compose
    assert 'if [ "${RUN_DB_MIGRATIONS:-true}" = "true" ]' in entrypoint
    assert ". /app/docker/prepare-env.sh" in entrypoint
    assert ". /app/docker/prepare-env.sh" in scheduler_entrypoint
    assert "DATABASE_URL: postgresql" not in base_compose
    assert "POSTGRES_PASSWORD:" in base_compose
    assert "quote(os.environ" in prepare_env
    assert "ARG APP_VERSION=1.2.0" in dockerfile


def test_preflight_redacts_injected_secrets_from_subprocess_output() -> None:
    env = {
        "POSTGRES_PASSWORD": "database-password-value",
        "WECHAT_APP_SECRET": "wechat-secret-value",
        "DATABASE_URL": "postgresql+psycopg://user:url-password@db:5432/zhongshu",
        "NORMAL_VALUE": "public-value",
    }
    sensitive = _sensitive_values(env)
    redacted = _redact(
        "database-password-value wechat-secret-value "
        "postgresql+psycopg://user:url-password@db:5432/zhongshu "
        "url-password public-value",
        sensitive,
    )
    assert "database-password-value" not in redacted
    assert "wechat-secret-value" not in redacted
    assert "url-password" not in redacted
    assert "postgresql+psycopg://" not in redacted
    assert "public-value" in redacted


def test_compose_database_url_is_derived_from_postgres_settings_with_matching_encoding() -> None:
    env = {
        "POSTGRES_USER": "zhong shu",
        "POSTGRES_PASSWORD": "p@ss/word#1",
        "POSTGRES_DB": "lead db",
    }
    expected = "postgresql+psycopg://zhong%20shu:p%40ss%2Fword%231@db:5432/lead%20db"
    assert derive_compose_database_url(env) == expected
    assert _database_url_from_postgres(env) == expected
    prepare_env = Path("docker/prepare-env.sh").read_text(encoding="utf-8")
    assert 'quote(os.environ["POSTGRES_USER"], safe="")' in prepare_env
    assert 'quote(os.environ["POSTGRES_PASSWORD"], safe="")' in prepare_env
    assert 'quote(os.environ["POSTGRES_DB"], safe="")' in prepare_env


def test_compose_database_preflight_runs_database_checks_inside_api_service(monkeypatch) -> None:
    monkeypatch.setattr("scripts.preflight_v12.shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    command = _compose_python_command(Path("/srv/app/.env"), ["scripts/reconcile_v12.py"])
    assert command[:2] == ["/usr/bin/docker", "compose"]
    assert "--env-file" in command
    assert "run" in command and "--rm" in command and "-T" in command
    assert command[-2:] == ["python", "scripts/reconcile_v12.py"]
    assert "api" in command
    assert "RUN_DB_MIGRATIONS=false" in command


def test_image_reference_parser_requires_exact_version_tag() -> None:
    assert image_tag("registry.example.com/app:1.2.0@sha256:" + "a" * 64) == "1.2.0"
    assert image_tag("registry.example.com:5000/team/app:1.2.9") == "1.2.9"
    assert image_tag("registry.example.com:5000/team/app@sha256:" + "a" * 64) is None


def test_scan_subject_image_id_is_strict_and_inspect_uses_docker_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = "sha256:" + "a" * 64
    subject = tmp_path / "scan-subject.json"
    subject.write_text(json.dumps({"image_id": expected}), encoding="utf-8")
    assert load_scan_subject_image_id(subject) == expected

    subject.write_text(json.dumps({"image_id": "sha256:not-a-digest"}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="image_id"):
        load_scan_subject_image_id(subject)

    class Result:
        returncode = 0
        stdout = json.dumps(
            {
                "Id": expected,
                "Config": {"Labels": {"org.opencontainers.image.version": "1.2.0"}},
            }
        )
        stderr = ""

    seen: list[str] = []

    def fake_run(command: list[str], **_: object) -> Result:
        seen.extend(command)
        return Result()

    monkeypatch.setattr("scripts.verify_production.subprocess.run", fake_run)
    version, actual, error = inspect_image_metadata(
        "docker", "registry.example.com/app:1.2.0@sha256:digest"
    )
    assert error is None
    assert version == "1.2.0"
    assert actual == expected
    assert seen[-1] == "{{json .}}"

    def invalid_utf8(*_: object, **__: object) -> Result:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr("scripts.verify_production.subprocess.run", invalid_utf8)
    version, actual, error = inspect_image_metadata("docker", "registry.example.com/app:1.2.0")
    assert version is None and actual is None
    assert error and "invalid UTF-8" in error


def test_deployment_persists_reconciliation_and_uses_compose_database_preflight() -> None:
    deployment = Path("docs/runbooks/DEPLOYMENT.md").read_text(encoding="utf-8")
    go_no_go = Path("docs/runbooks/V1.2_GO_NO_GO.md").read_text(encoding="utf-8")
    migration = Path("docs/runbooks/V1.2_MIGRATION_RUNBOOK.md").read_text(encoding="utf-8")
    preflight = Path("scripts/preflight_v12.py").read_text(encoding="utf-8")
    assert "> dist/v12-reconciliation.json" in deployment
    assert "python -m json.tool dist/v12-reconciliation.json" in deployment
    assert "--compose-database" in deployment
    assert "/tmp/v12-reconciliation.json" not in deployment
    assert "reconcile_status=$?" in migration
    assert 'exit "$reconcile_status"' in migration
    assert "reconciliation-before-backfill.json || true" not in migration
    assert "--require-image-digest" in preflight
    assert "--require-image-inspect" in preflight
    assert "--compose-database requires --scan-subject" in preflight
    assert '["--scan-subject", str(args.scan_subject.resolve())]' in preflight
    assert "--scan-subject scan-subject.json" in deployment
    assert "--scan-subject scan-subject.json" in go_no_go


def test_sprint6_runbooks_and_release_documents_exist() -> None:
    required = (
        "docs/quality/DEPENDENCY_RISK_ACCEPTANCE.md",
        "docs/runbooks/PRODUCTION_CHECKLIST_V1.2.md",
        "docs/runbooks/V1.2_MIGRATION_RUNBOOK.md",
        "docs/runbooks/V1.2_UAT.md",
        "docs/runbooks/V1.2_GO_NO_GO.md",
        "docs/runbooks/V1.2_ROLLBACK.md",
        "docs/runbooks/V1.2_POST_LAUNCH.md",
        "docs/release/RELEASE_NOTES_V1.2.0.md",
    )
    for relative in required:
        content = Path(relative).read_text(encoding="utf-8")
        assert len(content) > 500
    assert "V1.2" in Path("docs/runbooks/V1.2_GO_NO_GO.md").read_text(encoding="utf-8")


def test_openapi_is_generated_build_artifact_not_tracked_stale_json() -> None:
    assert not Path("docs/api/openapi.json").exists()
    exporter = Path("scripts/export_openapi.py").read_text(encoding="utf-8")
    assert "dist" in exporter and "openapi" in exporter
    assert "def openapi_text()" in exporter


def test_ci_contains_postgres_browser_dependency_evidence_and_packaging_gates() -> None:
    pr_workflow = Path(".github/workflows/v12-pr-ci.yml").read_text(encoding="utf-8")
    release_workflow = Path(".github/workflows/v12-release-ci.yml").read_text(encoding="utf-8")
    for workflow in (pr_workflow, release_workflow):
        assert "postgres:16-alpine" in workflow
        assert "baseline_v101.py" in workflow
        assert "migrate_v12_data.py" in workflow
        assert "browser_smoke_v12.py" in workflow
        assert "pip-audit" in workflow
        assert "requirements-browser.txt" in workflow
        assert "v12-postgres-verification.json" in workflow
        assert "fetch-depth: 0" in workflow
        assert "scripts/package_release.py" in workflow
        assert "release-package-${{ github.run_id }}" in workflow
        assert "cat requirements.txt requirements-postgres.txt requirements-browser.txt" not in workflow
        assert workflow.count("printf '\\n'") >= 3
        assert "--ignore-vuln PYSEC-2026-3552" in workflow
        assert workflow.count("--ignore-vuln") == 1
        assert "DEPENDENCY_RISK_ACCEPTANCE.md" in workflow
        assert "dist/openapi/openapi.json" in workflow
        assert "path: docs/api/openapi.json" not in workflow
        assert "dist/quality/pytest-output.txt" in workflow
        assert "dist/quality/migration-output.txt" in workflow
        assert "> pytest-output.txt" not in workflow
        assert "> migration-output.txt" not in workflow
    assert "--version V1.2.0-rc" in pr_workflow
    assert "--version V1.2.0" in release_workflow

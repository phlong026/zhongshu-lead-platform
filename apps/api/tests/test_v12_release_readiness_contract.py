from __future__ import annotations

from pathlib import Path

from scripts.preflight_v12 import (
    _compose_python_command,
    _database_url_from_postgres,
    _redact,
    _sensitive_values,
)
from scripts.validate_production_env import derive_compose_database_url


def test_production_compose_requires_reviewed_image_and_disables_implicit_migration() -> None:
    compose = Path("docker-compose.prod.yml").read_text(encoding="utf-8")
    entrypoint = Path("docker/entrypoint.sh").read_text(encoding="utf-8")
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "APP_IMAGE must reference the reviewed V1.2 image" in compose
    assert 'RUN_DB_MIGRATIONS: "false"' in compose
    assert 'if [ "${RUN_DB_MIGRATIONS:-true}" = "true" ]' in entrypoint
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


def test_compose_database_url_is_derived_from_postgres_settings_without_plaintext_logging() -> None:
    env = {
        "POSTGRES_USER": "zhong shu",
        "POSTGRES_PASSWORD": "p@ss/word",
        "POSTGRES_DB": "lead db",
    }
    expected = "postgresql+psycopg://zhong%20shu:p%40ss%2Fword@db:5432/lead%20db"
    assert derive_compose_database_url(env) == expected
    assert _database_url_from_postgres(env) == expected


def test_compose_database_preflight_runs_database_checks_inside_api_service(monkeypatch) -> None:
    monkeypatch.setattr("scripts.preflight_v12.shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    command = _compose_python_command(Path("/srv/app/.env"), ["scripts/reconcile_v12.py"])
    assert command[:2] == ["/usr/bin/docker", "compose"]
    assert "--env-file" in command
    assert "run" in command and "--rm" in command and "-T" in command
    assert command[-3:] == ["python", "scripts/reconcile_v12.py"][-3:]
    assert "api" in command
    assert "RUN_DB_MIGRATIONS=false" in command


def test_deployment_persists_reconciliation_and_uses_compose_database_preflight() -> None:
    deployment = Path("docs/runbooks/DEPLOYMENT.md").read_text(encoding="utf-8")
    assert "> dist/v12-reconciliation.json" in deployment
    assert "python -m json.tool dist/v12-reconciliation.json" in deployment
    assert "--compose-database" in deployment
    assert "/tmp/v12-reconciliation.json" not in deployment


def test_sprint6_runbooks_and_release_documents_exist() -> None:
    required = (
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
        assert "V1.2" in content
        assert len(content) > 500


def test_ci_contains_postgres_browser_and_dependency_security_gates() -> None:
    for relative in (".github/workflows/v12-pr-ci.yml", ".github/workflows/v12-release-ci.yml"):
        workflow = Path(relative).read_text(encoding="utf-8")
        assert "postgres:16-alpine" in workflow
        assert "baseline_v101.py" in workflow
        assert "migrate_v12_data.py" in workflow
        assert "browser_smoke_v12.py" in workflow
        assert "pip-audit" in workflow
        assert "requirements-browser.txt" in workflow

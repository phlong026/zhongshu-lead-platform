from __future__ import annotations

from pathlib import Path
import re

from fastapi.testclient import TestClient

from apps.api.src.main import app


def test_health_contracts():
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/health/live').json()['status'] == 'alive'
        assert client.get('/health/ready').json()['database'] == 'ok'


def test_deployment_files_exist():
    required = [
        'Dockerfile',
        'docker-compose.yml',
        'alembic.ini',
        'migrations/env.py',
        'migrations/versions/0001_initial_schema.py',
        'infra/nginx/default.conf',
        'docker/entrypoint.sh',
        'scripts/scheduler.py',
        'docs/runbooks/DEPLOYMENT.md',
    ]
    for name in required:
        assert Path(name).exists(), name


def test_nginx_reuses_upstream_connections_for_capacity() -> None:
    for config_path in (
        "infra/nginx/default.conf",
        "infra/nginx/production.conf.template",
        "infra/nginx/baota-proxy.conf.template",
    ):
        config = Path(config_path).read_text(encoding="utf-8")
        assert "upstream zhongshu_api" in config
        assert "keepalive 256;" in config
        assert "proxy_pass http://zhongshu_api" in config
        assert 'proxy_set_header Connection "";' in config or "proxy_set_header Connection $connection_upgrade;" in config


def test_nginx_template_mount_leaves_envsubst_destination_writable() -> None:
    base_compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    production_compose = Path("docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "/etc/nginx/conf.d/default.conf:ro" not in base_compose
    template_target = "/etc/nginx/templates/default.conf.template:ro"
    assert template_target in base_compose
    assert template_target in production_compose


def test_production_compose_uses_loopback_baota_gateway() -> None:
    base_compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    production_compose = Path("docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "127.0.0.1:${HTTP_PORT:-8080}:80" in base_compose
    assert "127.0.0.1:${HTTP_PORT:-80}:80" in production_compose
    assert "HTTPS_PORT" not in production_compose
    assert "./infra/nginx/baota-proxy.conf.template" in production_compose
    assert "./infra/certs" not in production_compose


def test_baota_health_checks_forward_the_public_host() -> None:
    config = Path("infra/nginx/baota-proxy.conf.template").read_text(encoding="utf-8")

    for location in ("/health/live", "/health/ready"):
        block = config.split(f"location = {location} {{", maxsplit=1)[1].split("}", maxsplit=1)[0]
        assert "proxy_set_header Host $host;" in block


def test_container_shell_scripts_are_checked_out_with_linux_line_endings():
    attributes = Path('.gitattributes').read_text(encoding='utf-8')
    assert '*.sh text eol=lf' in attributes

    scripts = sorted(Path('docker').glob('*.sh')) + sorted(Path('scripts').glob('*.sh'))
    assert scripts
    for script in scripts:
        content = script.read_bytes()
        assert content.startswith(b'#!/'), script
        assert b'\r\n' not in content, script


def test_migration_revision_identifiers_fit_alembic_version_column() -> None:
    """Keep revision values compatible with Alembic's default VARCHAR(32) table."""

    for migration in Path("migrations/versions").glob("*.py"):
        match = re.search(
            r'^revision\s*=\s*["\']([^"\']+)["\']',
            migration.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
        assert match is not None, migration
        assert len(match.group(1)) <= 32, migration

from __future__ import annotations

from pathlib import Path

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


def test_container_shell_scripts_are_checked_out_with_linux_line_endings():
    attributes = Path('.gitattributes').read_text(encoding='utf-8')
    assert '*.sh text eol=lf' in attributes

    scripts = sorted(Path('docker').glob('*.sh')) + sorted(Path('scripts').glob('*.sh'))
    assert scripts
    for script in scripts:
        content = script.read_bytes()
        assert content.startswith(b'#!/'), script
        assert b'\r\n' not in content, script

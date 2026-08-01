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

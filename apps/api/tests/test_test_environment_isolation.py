from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from apps.api.src.core.config import get_settings


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_standard_pytest_uses_deterministic_test_settings():
    settings = get_settings()

    assert os.environ["APP_ENV"] == "test"
    assert settings.app_env == "test"
    assert settings.app_base_url == "http://testserver"
    assert settings.database_url.startswith("sqlite:///")
    assert settings.trusted_host_list == ["testserver", "localhost", "127.0.0.1"]
    assert settings.object_storage_backend == "local"
    assert settings.legacy_write_enabled is True
    assert settings.wechat_dev_mock is True


def test_conftest_overrides_polluted_host_environment_before_application_imports():
    script = """
import os
os.environ.update({
    'APP_ENV': 'production',
    'APP_BASE_URL': 'https://prod.invalid',
    'DATABASE_URL': 'postgresql+psycopg://prod:secret@prod.invalid/prod',
    'TRUSTED_HOSTS': 'prod.invalid',
    'OBJECT_STORAGE_BACKEND': 's3',
    'LEGACY_WRITE_ENABLED': 'false',
    'WECHAT_DEV_MOCK': 'false',
})
import apps.api.tests.conftest  # noqa: F401
from apps.api.src.core.config import get_settings
settings = get_settings()
assert settings.app_env == 'test'
assert settings.app_base_url == 'http://testserver'
assert settings.database_url.startswith('sqlite:///')
assert settings.trusted_host_list == ['testserver', 'localhost', '127.0.0.1']
assert settings.object_storage_backend == 'local'
assert settings.legacy_write_enabled is True
assert settings.wechat_dev_mock is True
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr

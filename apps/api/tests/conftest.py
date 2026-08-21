from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


# Test configuration must be installed before any application module imports
# Settings/get_settings. Unconditional assignment deliberately prevents a
# developer's production .env or shell variables from changing pytest behavior.
_TEST_RUNTIME_ROOT = Path(tempfile.gettempdir()) / f"zhongshu-pytest-{os.getpid()}"
_TEST_ENVIRONMENT = {
    "APP_ENV": "test",
    "APP_BASE_URL": "http://testserver",
    "DATABASE_URL": f"sqlite:///{_TEST_RUNTIME_ROOT / 'application.db'}",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
    "CORS_ORIGINS": "http://testserver",
    "OBJECT_STORAGE_BACKEND": "local",
    "OBJECT_STORAGE_DIR": str(_TEST_RUNTIME_ROOT / "storage"),
    "LEGACY_WRITE_ENABLED": "true",
    "WECHAT_DEV_MOCK": "true",
    "WECHAT_APP_ID": "wx-test-only",
    "WECHAT_APP_SECRET": "test-only-not-a-secret",
    "WECHAT_OAUTH_REDIRECT_URI": "http://testserver/api/v1/auth/wechat/callback",
    "WECHAT_OAUTH_SCOPE": "snsapi_base",
    "FEISHU_ENABLED": "false",
    "FEISHU_DEV_MOCK": "true",
    "AUTO_CREATE_SCHEMA": "true",
    "JWT_SECRET": "pytest-jwt-secret-not-for-production-2026",
    "FIELD_ENCRYPTION_KEY": "pytest-field-key-not-for-production",
    "PHONE_HASH_SECRET": "pytest-phone-hash-not-for-production",
    "PHONE_FINGERPRINT_SECRET": "pytest-phone-fingerprint-not-for-production",
    "S3_ENDPOINT_URL": "",
    "S3_ACCESS_KEY_ID": "",
    "S3_SECRET_ACCESS_KEY": "",
}
os.environ.update(_TEST_ENVIRONMENT)

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from apps.api.src.core import auth_models, invite_models, models  # noqa: E402,F401
from apps.api.src.core.config import get_settings  # noqa: E402
from apps.api.src.core.database import Base  # noqa: E402
from apps.api.src.services.rbac import seed_rbac  # noqa: E402

# Defensive cache reset for runners/plugins that imported config before this
# conftest. Production defaults remain unchanged; only this pytest process is
# normalized.
get_settings.cache_clear()


@pytest.fixture()
def db(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        seed_rbac(session)
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """HTTP client backed by an isolated database and private local storage."""
    from fastapi.testclient import TestClient

    from apps.api.src.core.database import get_db
    from apps.api.src.main import app
    from apps.api.src.services.bootstrap import seed_demo
    import apps.api.src.integrations.wechat as wechat_module
    import apps.api.src.services.storage as storage_module

    engine = create_engine(
        f"sqlite:///{tmp_path / 'http-e2e.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    with factory() as session:
        seed_demo(session)
        session.commit()

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(storage_module.settings, "object_storage_backend", "local")
    monkeypatch.setattr(storage_module.settings, "object_storage_dir", str(tmp_path / "private-storage"))
    # HTTP OAuth security tests need the authorization URL to be constructible,
    # but must never depend on a real WeChat credential or outbound exchange.
    monkeypatch.setattr(wechat_module.settings, "wechat_app_id", "wx-test-only")
    monkeypatch.setattr(
        wechat_module.settings,
        "wechat_oauth_redirect_uri",
        "http://testserver/api/v1/auth/wechat/callback",
    )
    monkeypatch.setattr(wechat_module.settings, "wechat_oauth_scope", "snsapi_base")
    client = TestClient(app, base_url="http://testserver")
    try:
        yield client, factory
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()

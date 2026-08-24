from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.core.database import Base
from apps.api.src.core import auth_models, models  # noqa: F401
from apps.api.src.services.rbac import seed_rbac


@pytest.fixture(autouse=True)
def _reset_process_local_rate_limiters():
    """清空进程内限流/节流桶，避免同进程测试互相污染窗口计数（N8/N11）。"""

    from apps.api.src.routers import auth as auth_router

    auth_router._CONFIRM_START_BUCKETS.clear()
    auth_router._CONFIRM_START_IP_BUCKETS.clear()
    auth_router._CALLBACK_AUDIT_THROTTLE.clear()
    yield
    auth_router._CONFIRM_START_BUCKETS.clear()
    auth_router._CONFIRM_START_IP_BUCKETS.clear()
    auth_router._CALLBACK_AUDIT_THROTTLE.clear()


@pytest.fixture()
def db(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        seed_rbac(session)
        session.commit()
        yield session


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """HTTP client backed by an isolated database and private local storage."""
    from fastapi.testclient import TestClient

    from apps.api.src.core.database import get_db
    from apps.api.src.main import app, settings
    from apps.api.src.services.bootstrap import seed_demo
    import apps.api.src.core.legacy_guard as legacy_guard_module
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
    # Browser session tests must not inherit production Secure-cookie behavior
    # from an operator's private .env.
    monkeypatch.setattr(settings, "app_env", "test")
    # Legacy HTTP regression tests must not inherit the operator's production
    # .env. Tests for the production guard opt out explicitly per scenario.
    monkeypatch.setattr(legacy_guard_module.settings, "legacy_write_enabled", True)
    monkeypatch.setattr(storage_module.settings, "object_storage_backend", "local")
    monkeypatch.setattr(storage_module.settings, "object_storage_dir", str(tmp_path / "private-storage"))
    # HTTP OAuth security tests need the authorization URL to be constructible,
    # but must never depend on a real WeChat credential or outbound exchange.
    monkeypatch.setattr(wechat_module.settings, "wechat_app_id", "wx-test-only")
    monkeypatch.setattr(
        wechat_module.settings,
        "wechat_oauth_redirect_uri",
        "https://testserver/api/v1/auth/wechat/callback",
    )
    monkeypatch.setattr(wechat_module.settings, "wechat_oauth_scope", "snsapi_base")
    allowed_host = next(
        (host for host in settings.trusted_host_list if host and "*" not in host),
        "localhost",
    )
    client = TestClient(app, base_url=f"http://{allowed_host}")
    try:
        yield client, factory
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()

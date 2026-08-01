from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.core.database import Base
from apps.api.src.core import models  # noqa: F401
from apps.api.src.services.rbac import seed_rbac


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
    from apps.api.src.main import app
    from apps.api.src.services.bootstrap import seed_demo
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
    client = TestClient(app)
    try:
        yield client, factory
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()

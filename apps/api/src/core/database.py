from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import Settings, get_settings


def database_engine_options(settings: Settings) -> dict[str, object]:
    options: dict[str, object] = {
        "future": True,
        "pool_pre_ping": True,
        "connect_args": {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    }
    if not settings.database_url.startswith("sqlite"):
        options.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout_seconds,
        )
    return options


settings = get_settings()
engine = create_engine(settings.database_url, **database_engine_options(settings))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_database() -> None:
    from . import auth_models  # noqa: F401
    from . import invite_models  # noqa: F401
    from . import models  # noqa: F401
    from . import models_v12  # noqa: F401
    from . import reward_models_v12  # noqa: F401

    if settings.app_env.lower() == "production" and not settings.auto_create_schema:
        return
    Base.metadata.create_all(bind=engine)

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.api.src.core.config import Settings
from apps.api.src.core.database import database_engine_options


def test_postgres_engine_pool_matches_sync_worker_capacity() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:password@db:5432/zhongshu",
    )

    options = database_engine_options(settings)

    assert options["pool_size"] + options["max_overflow"] == 40
    assert options["pool_timeout"] == 30


def test_sqlite_engine_does_not_receive_queue_pool_options() -> None:
    settings = Settings(_env_file=None, database_url="sqlite+pysqlite:///:memory:")

    options = database_engine_options(settings)

    assert "pool_size" not in options
    assert "max_overflow" not in options
    assert "pool_timeout" not in options


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("database_pool_size", 0),
        ("database_pool_size", 41),
        ("database_max_overflow", -1),
        ("database_max_overflow", 41),
        ("database_pool_timeout_seconds", 0),
        ("database_pool_timeout_seconds", 61),
        ("in_flight_queue_timeout_seconds", 0),
        ("in_flight_queue_timeout_seconds", 31),
    ),
)
def test_database_pool_settings_reject_unsafe_bounds(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_database_pool_rejects_more_than_one_sync_worker_budget() -> None:
    with pytest.raises(ValidationError, match="must not exceed 40 per process"):
        Settings(_env_file=None, database_pool_size=21, database_max_overflow=20)


def test_threadpool_must_fit_inside_each_worker_connection_budget() -> None:
    with pytest.raises(ValidationError, match="must not exceed the per-process database connection budget"):
        Settings(
            _env_file=None,
            database_pool_size=15,
            database_max_overflow=15,
            sync_threadpool_tokens=31,
        )


def test_in_flight_limit_must_leave_requests_inside_the_connection_budget() -> None:
    with pytest.raises(ValidationError, match="MAX_IN_FLIGHT_REQUESTS must not exceed"):
        Settings(
            _env_file=None,
            database_pool_size=10,
            database_max_overflow=10,
            sync_threadpool_tokens=20,
            max_in_flight_requests=21,
        )


def test_worker_connection_budget_leaves_postgres_headroom() -> None:
    settings = Settings(
        _env_file=None,
        database_pool_size=9,
        database_max_overflow=9,
        sync_threadpool_tokens=18,
        max_in_flight_requests=18,
        web_concurrency=5,
    )

    assert settings.web_concurrency * (settings.database_pool_size + settings.database_max_overflow) == 90

    with pytest.raises(ValidationError, match="must not exceed 90"):
        Settings(
            _env_file=None,
            database_pool_size=10,
            database_max_overflow=9,
            sync_threadpool_tokens=18,
            max_in_flight_requests=18,
            web_concurrency=5,
        )

    with pytest.raises(ValidationError, match="WEB_CONCURRENCY must be between 1 and 5"):
        Settings(
            _env_file=None,
            database_pool_size=7,
            database_max_overflow=7,
            sync_threadpool_tokens=14,
            max_in_flight_requests=14,
            web_concurrency=6,
        )


def test_compose_reserves_a_small_pool_for_scheduler() -> None:
    compose = open("docker-compose.yml", encoding="utf-8").read()

    assert 'max_connections=${POSTGRES_MAX_CONNECTIONS:-100}' in compose
    assert "DATABASE_POOL_SIZE: ${DATABASE_POOL_SIZE:-20}" in compose
    assert "DATABASE_MAX_OVERFLOW: ${DATABASE_MAX_OVERFLOW:-20}" in compose
    assert "DATABASE_POOL_TIMEOUT_SECONDS: ${DATABASE_POOL_TIMEOUT_SECONDS:-30}" in compose
    assert '"${WEB_CONCURRENCY:-1}"' in compose
    assert "--no-access-log" in compose
    assert "SYNC_THREADPOOL_TOKENS: ${SYNC_THREADPOOL_TOKENS:-40}" in compose
    assert "MAX_IN_FLIGHT_REQUESTS: ${MAX_IN_FLIGHT_REQUESTS:-32}" in compose
    assert "IN_FLIGHT_QUEUE_TIMEOUT_SECONDS: ${IN_FLIGHT_QUEUE_TIMEOUT_SECONDS:-10}" in compose
    assert "DATABASE_POOL_SIZE: ${SCHEDULER_DATABASE_POOL_SIZE:-2}" in compose
    assert "DATABASE_MAX_OVERFLOW: ${SCHEDULER_DATABASE_MAX_OVERFLOW:-2}" in compose
    assert "SYNC_THREADPOOL_TOKENS: ${SCHEDULER_SYNC_THREADPOOL_TOKENS:-4}" in compose

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from apps.api.src.main import app, settings


def test_duplicate_uvicorn_access_log_is_disabled() -> None:
    access_logger = logging.getLogger("uvicorn.access")

    assert access_logger.disabled is True
    assert access_logger.propagate is False


def test_request_log_identifies_the_serving_worker(caplog, monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "test")
    allowed_host = next(
        (host for host in settings.trusted_host_list if host and "*" not in host),
        "localhost",
    )
    with caplog.at_level(logging.INFO, logger="zhongshu.http"):
        with TestClient(app, base_url=f"http://{allowed_host}") as client:
            response = client.get("/health/live")

    assert response.status_code == 200
    request_log = next(record for record in caplog.records if record.getMessage() == "request_completed")
    assert isinstance(request_log.worker_pid, int)
    assert request_log.worker_pid > 0

from __future__ import annotations

import pytest

from apps.api.src.core.errors import AppError


def _login_admin(client) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin123!"},
    )
    assert response.status_code == 200, response.text


def test_disabled_feishu_sync_returns_503_and_diagnostics_remain_available(api_client, monkeypatch) -> None:
    client, _ = api_client
    import apps.api.src.integrations.feishu as feishu_module

    monkeypatch.setattr(feishu_module.settings, "feishu_enabled", False)
    monkeypatch.setattr(feishu_module.settings, "feishu_dev_mock", False)
    _login_admin(client)

    response = client.post("/api/v1/leads/feishu/sync")
    assert response.status_code == 503
    assert response.json()["code"] == "FEISHU_DISABLED"

    diagnostics = client.get("/api/v1/leads/feishu/diagnostics")
    assert diagnostics.status_code == 200
    assert diagnostics.json()["data"]["enabled"] is False


def test_mock_sync_is_unavailable_when_mock_switch_is_off(api_client, monkeypatch) -> None:
    client, _ = api_client
    import apps.api.src.routers.leads as leads_router

    monkeypatch.setattr(leads_router.settings, "feishu_dev_mock", False)
    _login_admin(client)
    response = client.post(
        "/api/v1/leads/feishu/mock-sync",
        json={"records": [], "field_mapping": {}},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "FEISHU_MOCK_DISABLED"


def test_direct_feishu_import_service_is_blocked_when_legacy_writes_are_disabled(db, monkeypatch) -> None:
    import apps.api.src.services.feishu_sync_service as sync_service

    monkeypatch.setattr(sync_service.settings, "legacy_write_enabled", False)
    monkeypatch.setattr(sync_service.settings, "feishu_enabled", True)
    with pytest.raises(AppError) as exc:
        sync_service.fetch_and_import_feishu(db)
    assert exc.value.code == "LEGACY_WRITE_DISABLED"
    assert exc.value.status_code == 410

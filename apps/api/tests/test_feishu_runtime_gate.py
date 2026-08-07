from __future__ import annotations


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

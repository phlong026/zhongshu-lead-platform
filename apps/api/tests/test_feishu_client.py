from __future__ import annotations

import httpx

from apps.api.src.integrations.feishu import FeishuClient


def test_feishu_client_paginates_and_caches_token(monkeypatch):
    import apps.api.src.integrations.feishu as module

    monkeypatch.setattr(module.settings, "feishu_dev_mock", False)
    monkeypatch.setattr(module.settings, "feishu_app_id", "app-id")
    monkeypatch.setattr(module.settings, "feishu_app_secret", "secret")
    monkeypatch.setattr(module.settings, "feishu_app_token", "bitable-app")
    monkeypatch.setattr(module.settings, "feishu_table_id", "table")
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path.endswith("tenant_access_token/internal"):
            token_calls += 1
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "tenant-token", "expire": 7200})
        page_token = request.url.params.get("page_token")
        if not page_token:
            return httpx.Response(200, json={"code": 0, "data": {"items": [{"record_id": "r1", "fields": {"手机号": "13800138000"}}], "has_more": True, "page_token": "next"}})
        return httpx.Response(200, json={"code": 0, "data": {"items": [{"record_id": "r2", "fields": {}}], "has_more": False}})

    client = FeishuClient(transport=httpx.MockTransport(handler))
    records = list(client.iter_records(page_size=100))
    assert [item.record_id for item in records] == ["r1", "r2"]
    assert token_calls == 1


def test_feishu_diagnostics_exposes_no_secrets(monkeypatch):
    import apps.api.src.integrations.feishu as module

    monkeypatch.setattr(module.settings, "feishu_app_id", "app-id")
    monkeypatch.setattr(module.settings, "feishu_app_secret", "secret")
    monkeypatch.setattr(module.settings, "feishu_app_token", "token")
    monkeypatch.setattr(module.settings, "feishu_table_id", "table")
    data = FeishuClient().diagnostics()
    assert data["configured"] is True
    assert "secret" not in data

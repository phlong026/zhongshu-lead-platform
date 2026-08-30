from __future__ import annotations

import httpx
import pytest

from apps.api.src.core.errors import AppError
from apps.api.src.integrations.feishu import FeishuClient


def test_feishu_client_paginates_and_caches_token(monkeypatch):
    import apps.api.src.integrations.feishu as module

    monkeypatch.setattr(module.settings, "feishu_enabled", True)
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
    records = list(client.iter_records(page_size=100, view_id="view-customer"))
    assert [item.record_id for item in records] == ["r1", "r2"]
    assert token_calls == 1


def test_feishu_client_limits_records_to_the_named_customer_view(monkeypatch):
    import apps.api.src.integrations.feishu as module

    monkeypatch.setattr(module.settings, "feishu_enabled", True)
    monkeypatch.setattr(module.settings, "feishu_dev_mock", False)
    monkeypatch.setattr(module.settings, "feishu_app_id", "app-id")
    monkeypatch.setattr(module.settings, "feishu_app_secret", "secret")
    monkeypatch.setattr(module.settings, "feishu_app_token", "bitable-app")
    monkeypatch.setattr(module.settings, "feishu_table_id", "table")
    record_view_ids: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "tenant-token", "expire": 7200})
        if request.url.path.endswith("/views"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "items": [
                            {"view_id": "view-other", "view_name": "其他视图"},
                            {"view_id": "view-customer", "view_name": "客户视图"},
                        ],
                        "has_more": False,
                    },
                },
            )
        record_view_ids.append(request.url.params.get("view_id"))
        return httpx.Response(200, json={"code": 0, "data": {"items": [], "has_more": False}})

    client = FeishuClient(transport=httpx.MockTransport(handler))
    view_id = client.resolve_view_id("客户视图")
    list(client.iter_records(view_id=view_id))

    assert view_id == "view-customer"
    assert record_view_ids == ["view-customer"]


def test_feishu_client_blocks_reads_and_writes_when_disabled(monkeypatch):
    import apps.api.src.integrations.feishu as module

    monkeypatch.setattr(module.settings, "feishu_enabled", False)
    monkeypatch.setattr(module.settings, "feishu_dev_mock", False)
    client = FeishuClient(transport=httpx.MockTransport(lambda request: pytest.fail("disabled integration made an HTTP request")))

    with pytest.raises(AppError) as read_error:
        list(client.iter_records())
    assert read_error.value.code == "FEISHU_DISABLED"
    assert read_error.value.status_code == 503

    with pytest.raises(AppError) as write_error:
        client.write_back("record-id", {"状态": "已导入"})
    assert write_error.value.code == "FEISHU_DISABLED"


def test_feishu_diagnostics_exposes_enable_state_without_secrets(monkeypatch):
    import apps.api.src.integrations.feishu as module

    monkeypatch.setattr(module.settings, "feishu_enabled", False)
    monkeypatch.setattr(module.settings, "feishu_app_id", "app-id")
    monkeypatch.setattr(module.settings, "feishu_app_secret", "secret")
    monkeypatch.setattr(module.settings, "feishu_app_token", "token")
    monkeypatch.setattr(module.settings, "feishu_table_id", "table")
    data = FeishuClient().diagnostics()
    assert data["enabled"] is False
    assert data["configured"] is True
    assert "secret" not in data


def test_feishu_failure_details_do_not_reflect_table_identifiers(monkeypatch):
    import apps.api.src.integrations.feishu as module

    monkeypatch.setattr(module.settings, "feishu_enabled", True)
    monkeypatch.setattr(module.settings, "feishu_dev_mock", False)
    monkeypatch.setattr(module.settings, "feishu_app_id", "app-id")
    monkeypatch.setattr(module.settings, "feishu_app_secret", "secret")
    monkeypatch.setattr(module.settings, "feishu_app_token", "private-base-token")
    monkeypatch.setattr(module.settings, "feishu_table_id", "private-table-id")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(
                200,
                json={"code": 0, "tenant_access_token": "tenant-token", "expire": 7200},
            )
        return httpx.Response(500, json={"code": 999})

    client = FeishuClient(transport=httpx.MockTransport(handler))
    with pytest.raises(AppError) as error:
        list(client.iter_records())

    assert error.value.code == "FEISHU_UNAVAILABLE"
    assert "private-base-token" not in str(error.value.details)
    assert "private-table-id" not in str(error.value.details)

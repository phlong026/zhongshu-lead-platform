from __future__ import annotations

from apps.api.src.core.legacy_guard import is_legacy_write


def test_legacy_write_classifier_blocks_only_legacy_mutations() -> None:
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert is_legacy_write(method, "/api/v1/verification/tasks") is True
        assert is_legacy_write(method, "/api/v1/returns/return-1/submit") is True
        assert is_legacy_write(method, "/api/v1/claims/assignments/a-1") is True
        assert is_legacy_write(method, "/api/v1/dispatch/leads/lead-1") is True
        assert is_legacy_write(method, "/api/v1/leads/feishu/mock-sync") is True

    for method in ("GET", "HEAD", "OPTIONS"):
        assert is_legacy_write(method, "/api/v1/verification/tasks") is False
        assert is_legacy_write(method, "/api/v1/returns/return-1") is False

    assert is_legacy_write("POST", "/api/v1/v1.2/returns/assignments/a-1/draft") is False
    assert is_legacy_write("POST", "/api/v1/v1.2/assignments/a-1/claim") is False
    assert is_legacy_write("POST", "/api/v1/auth/login") is False
    assert is_legacy_write("POST", "/api/v1/followups/assignments/a-1") is False
    assert is_legacy_write("POST", "/api/v1/points/recharge") is False


def test_default_web_entries_route_to_v12_and_legacy_is_explicit(api_client) -> None:
    client, _ = api_client

    admin = client.get("/admin/", follow_redirects=False)
    assert admin.status_code == 302
    assert admin.headers["location"] == "/admin/v12-operations.html"

    h5 = client.get("/h5/", follow_redirects=False)
    assert h5.status_code == 302
    assert h5.headers["location"] == "/h5/v12-workbench.html"

    admin_legacy = client.get("/admin/legacy", follow_redirects=False)
    assert admin_legacy.status_code == 302
    assert admin_legacy.headers["location"] == "/admin/index.html"

    h5_legacy = client.get("/h5/legacy", follow_redirects=False)
    assert h5_legacy.status_code == 302
    assert h5_legacy.headers["location"] == "/h5/index.html"


def test_production_legacy_mutations_fail_closed_without_blocking_reads_or_v12(
    api_client,
    monkeypatch,
) -> None:
    client, _ = api_client
    import apps.api.src.core.legacy_guard as legacy_guard

    monkeypatch.setattr(legacy_guard.settings, "app_env", "production")
    monkeypatch.setattr(legacy_guard.settings, "legacy_write_enabled", False)

    legacy_posts = (
        "/api/v1/verification/tasks",
        "/api/v1/returns/missing/submit",
        "/api/v1/claims/assignments/missing",
        "/api/v1/dispatch/leads/missing",
        "/api/v1/leads/feishu/mock-sync",
    )
    for path in legacy_posts:
        response = client.post(path, json={})
        assert response.status_code == 410, path
        assert response.json()["code"] == "LEGACY_WRITE_DISABLED"

    legacy_read = client.get("/api/v1/verification/tasks")
    assert legacy_read.status_code != 410
    assert legacy_read.json()["code"] != "LEGACY_WRITE_DISABLED"

    v12_write = client.post(
        "/api/v1/v1.2/returns/assignments/missing/draft",
        json={"reason_code": "EMPTY_NUMBER", "description": "测试生产 V1.2 写路径未被 Legacy 门禁误伤"},
    )
    assert v12_write.status_code != 410
    assert v12_write.json()["code"] != "LEGACY_WRITE_DISABLED"

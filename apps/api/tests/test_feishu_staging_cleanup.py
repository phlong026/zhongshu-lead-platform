from __future__ import annotations

from apps.api.src.core.models import (
    Lead,
    VerificationTask,
)
from apps.api.src.core.security import encrypt_text, hash_phone


def _login_admin(client) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin123!"},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def _lead(*, name: str, phone: str, source_type: str = "FEISHU") -> Lead:
    return Lead(
        source_type=source_type,
        customer_name=name,
        phone_encrypted=encrypt_text(phone),
        phone_hash=hash_phone(phone),
        status="IMPORTED",
        raw_payload={},
    )


def test_feishu_staging_cleanup_is_read_only(api_client, monkeypatch) -> None:
    client, factory = api_client
    import apps.api.src.core.legacy_guard as legacy_guard

    monkeypatch.setattr(legacy_guard.settings, "legacy_write_enabled", False)
    admin = _login_admin(client)

    with factory() as db:
        removable = _lead(name="只读预览记录", phone="13800138000")
        blocked = _lead(name="有关联暂存", phone="13800138001")
        db.add_all([removable, blocked])
        db.flush()
        db.add(VerificationTask(lead_id=blocked.id, status="PENDING"))
        db.commit()
        removable_id = removable.id
        blocked_id = blocked.id

    preview = client.get("/api/v1/leads/staging-cleanup-preview", headers=admin)
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()["data"]
    assert preview_data["deletable_count"] == 1
    assert preview_data["blocked_count"] == 1
    assert "cleanup_token" not in preview_data

    response = client.post(
        "/api/v1/leads/staging-cleanup",
        headers=admin,
        json={},
    )
    assert response.status_code == 410
    assert response.json()["code"] == "LEGACY_WRITE_DISABLED"

    with factory() as db:
        assert db.get(Lead, removable_id) is not None
        assert db.get(Lead, blocked_id) is not None


def test_feishu_staging_cleanup_preview_ignores_non_feishu_sources(api_client) -> None:
    client, factory = api_client
    admin = _login_admin(client)

    with factory() as db:
        db.add(_lead(name="飞书暂存", phone="13800138011"))
        db.add(_lead(name="平台暂存", phone="13800138012", source_type="PLATFORM"))
        db.commit()

    preview = client.get("/api/v1/leads/staging-cleanup-preview", headers=admin)
    assert preview.status_code == 200, preview.text
    assert preview.json()["data"]["candidate_count"] == 1

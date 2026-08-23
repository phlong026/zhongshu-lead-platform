from __future__ import annotations

from sqlalchemy import select

from apps.api.src.core.models import AuditLog, Lead, VerificationTask
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


def test_feishu_staging_cleanup_previews_and_deletes_only_unreferenced_rows(api_client) -> None:
    client, factory = api_client
    admin = _login_admin(client)

    with factory() as db:
        removable = _lead(name="可清理暂存", phone="13800138001")
        blocked = _lead(name="有关联暂存", phone="13800138002")
        other_source = _lead(
            name="平台暂存",
            phone="13800138003",
            source_type="PLATFORM",
        )
        db.add_all([removable, blocked, other_source])
        db.flush()
        db.add(VerificationTask(lead_id=blocked.id, status="PENDING"))
        db.commit()
        removable_id = removable.id
        blocked_id = blocked.id
        other_source_id = other_source.id

    preview = client.get("/api/v1/leads/staging-cleanup-preview", headers=admin)
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()["data"]
    assert preview_data["deletable_count"] == 1
    assert preview_data["blocked_count"] == 1

    unconfirmed = client.post(
        "/api/v1/leads/staging-cleanup",
        headers=admin,
        json={"confirmed": False, "expected_deletable_count": 1},
    )
    assert unconfirmed.status_code == 422
    assert unconfirmed.json()["code"] == "STAGING_CLEANUP_CONFIRM_REQUIRED"

    stale_preview = client.post(
        "/api/v1/leads/staging-cleanup",
        headers=admin,
        json={"confirmed": True, "expected_deletable_count": 2},
    )
    assert stale_preview.status_code == 409
    assert stale_preview.json()["code"] == "STAGING_CLEANUP_PREVIEW_STALE"

    cleaned = client.post(
        "/api/v1/leads/staging-cleanup",
        headers=admin,
        json={"confirmed": True, "expected_deletable_count": 1},
    )
    assert cleaned.status_code == 200, cleaned.text
    assert cleaned.json()["data"]["deleted_count"] == 1

    with factory() as db:
        assert db.get(Lead, removable_id) is None
        assert db.get(Lead, blocked_id) is not None
        assert db.get(Lead, other_source_id) is not None
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "FEISHU_STAGING_CLEANUP")
        )
        assert audit is not None
        assert audit.after_json["deleted_count"] == 1

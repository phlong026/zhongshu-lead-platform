from __future__ import annotations

from sqlalchemy import select

from apps.api.src.core.models import (
    AuditLog,
    Lead,
    LeadDuplicateRelation,
    VerificationTask,
)
from apps.api.src.core.models_v12 import LeadDedupEvent
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
        duplicate_relation = LeadDuplicateRelation(
            lead_id=removable.id,
            duplicate_lead_id=other_source.id,
            reason="PHONE_HASH",
        )
        dedup_event = LeadDedupEvent(
            lead_id=removable.id,
            phone_fingerprint="fingerprint-removable",
            checkpoint="IMPORT",
            decision="ALLOW",
            matched_lead_id=other_source.id,
            details_json={},
        )
        db.add_all([duplicate_relation, dedup_event])
        db.commit()
        removable_id = removable.id
        blocked_id = blocked.id
        other_source_id = other_source.id
        duplicate_relation_id = duplicate_relation.id
        dedup_event_id = dedup_event.id

    preview = client.get("/api/v1/leads/staging-cleanup-preview", headers=admin)
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()["data"]
    assert preview_data["deletable_count"] == 1
    assert preview_data["blocked_count"] == 1
    cleanup_token = preview_data["cleanup_token"]

    unconfirmed = client.post(
        "/api/v1/leads/staging-cleanup",
        headers=admin,
        json={
            "confirmed": False,
            "expected_deletable_count": 1,
            "cleanup_token": cleanup_token,
        },
    )
    assert unconfirmed.status_code == 422
    assert unconfirmed.json()["code"] == "STAGING_CLEANUP_CONFIRM_REQUIRED"

    stale_preview = client.post(
        "/api/v1/leads/staging-cleanup",
        headers=admin,
        json={
            "confirmed": True,
            "expected_deletable_count": 2,
            "cleanup_token": cleanup_token,
        },
    )
    assert stale_preview.status_code == 409
    assert stale_preview.json()["code"] == "STAGING_CLEANUP_PREVIEW_STALE"

    cleaned = client.post(
        "/api/v1/leads/staging-cleanup",
        headers=admin,
        json={
            "confirmed": True,
            "expected_deletable_count": 1,
            "cleanup_token": cleanup_token,
        },
    )
    assert cleaned.status_code == 200, cleaned.text
    assert cleaned.json()["data"]["deleted_count"] == 1

    with factory() as db:
        assert db.get(Lead, removable_id) is None
        assert db.get(Lead, blocked_id) is not None
        assert db.get(Lead, other_source_id) is not None
        assert db.get(LeadDuplicateRelation, duplicate_relation_id) is None
        assert db.get(LeadDedupEvent, dedup_event_id) is None
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "FEISHU_STAGING_CLEANUP")
        )
        assert audit is not None
        assert audit.after_json["deleted_count"] == 1


def test_feishu_staging_cleanup_rejects_same_count_with_different_leads(api_client) -> None:
    client, factory = api_client
    admin = _login_admin(client)

    with factory() as db:
        original = _lead(name="原预览客资", phone="13800138011")
        db.add(original)
        db.commit()
        original_id = original.id

    preview = client.get("/api/v1/leads/staging-cleanup-preview", headers=admin)
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()["data"]
    assert preview_data["deletable_count"] == 1

    with factory() as db:
        original = db.get(Lead, original_id)
        assert original is not None
        original.source_type = "PLATFORM"
        replacement = _lead(name="新进客资", phone="13800138012")
        db.add(replacement)
        db.commit()
        replacement_id = replacement.id

    stale = client.post(
        "/api/v1/leads/staging-cleanup",
        headers=admin,
        json={
            "confirmed": True,
            "expected_deletable_count": 1,
            "cleanup_token": preview_data["cleanup_token"],
        },
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["code"] == "STAGING_CLEANUP_PREVIEW_STALE"

    with factory() as db:
        assert db.get(Lead, original_id) is not None
        assert db.get(Lead, replacement_id) is not None

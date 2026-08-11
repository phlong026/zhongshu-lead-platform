from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import func, select

from apps.api.src.core.enums import AssignmentStatus
from apps.api.src.core.models import (
    Assignment,
    AssignmentEvent,
    AuditLog,
    Company,
    Lead,
    NotificationOutbox,
    PointsAccount,
    User,
)
from apps.api.src.core.models_v12 import CompanyLeadCapability, CompanyServiceAreaV12
from apps.api.src.core.security import encrypt_text, fingerprint_phone, hash_phone
from apps.api.src.core.v12_enums import LeadSourceKind, LeadV12Status
from apps.api.src.routers import v12_dispatch as v12_dispatch_router


def _v12_lead(*, user_id: str, phone: str, status: str) -> Lead:
    now = datetime.now(timezone.utc)
    return Lead(
        source_type=LeadSourceKind.PLATFORM_MANUAL.value,
        source_kind=LeadSourceKind.PLATFORM_MANUAL.value,
        submitter_user_id=user_id,
        customer_name="接口隐私测试客户",
        phone_encrypted=encrypt_text(phone),
        phone_hash=hash_phone(phone),
        phone_fingerprint=fingerprint_phone(phone),
        consent_confirmed=True,
        city="上海市",
        region_code="310000",
        category_code="OLD_RENOVATION",
        brand_code="ZHONGSHU",
        need_summary="接口字段隔离测试",
        status=status,
        review_status="APPROVED",
        duplicate_status="CLEAR",
        imported_at=now,
        submitted_at=now,
        raw_payload={},
    )


def _login(client, username: str, password: str) -> None:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200


def test_masked_assignment_phone_reuses_only_masked_decryption(monkeypatch) -> None:
    calls: list[str] = []

    def fake_decrypt(value: str) -> str:
        calls.append(value)
        return "13800138000"

    monkeypatch.setattr(v12_dispatch_router, "decrypt_text", fake_decrypt)
    v12_dispatch_router._masked_encrypted_phone.cache_clear()
    try:
        assert v12_dispatch_router._masked_encrypted_phone("encrypted-phone") == "138****8000"
        assert v12_dispatch_router._masked_encrypted_phone("encrypted-phone") == "138****8000"
        assert calls == ["encrypted-phone"]
    finally:
        v12_dispatch_router._masked_encrypted_phone.cache_clear()


def test_assignment_detail_query_omits_unused_large_columns() -> None:
    statement = str(
        v12_dispatch_router._assignment_detail_projection("assignment-id", "company-id")
    )

    assert "assignments.lead_snapshot" not in statement
    assert "leads.raw_payload" not in statement
    assert "leads.phone_hash" not in statement
    assert "leads.phone_encrypted" in statement
    assert "assignments.company_id" in statement


def _prepare_dispatch_lead(factory, *, phone: str) -> tuple[str, str]:
    with factory() as db:
        company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        operation = db.scalar(select(User).where(User.username == "operation"))
        assert company is not None and operation is not None
        if not db.scalar(
            select(CompanyLeadCapability).where(
                CompanyLeadCapability.company_id == company.id,
                CompanyLeadCapability.capability_code == "LEAD_RECEIVER",
            )
        ):
            db.add(
                CompanyLeadCapability(
                    company_id=company.id,
                    capability_code="LEAD_RECEIVER",
                    active=True,
                    review_status="APPROVED",
                )
            )
        if not db.scalar(
            select(CompanyServiceAreaV12).where(
                CompanyServiceAreaV12.company_id == company.id,
                CompanyServiceAreaV12.region_code == "310000",
            )
        ):
            db.add(
                CompanyServiceAreaV12(
                    company_id=company.id,
                    region_code="310000",
                    region_level="CITY",
                    is_primary_city=True,
                    active=True,
                    review_status="APPROVED",
                )
            )
        account = db.scalar(select(PointsAccount).where(PointsAccount.company_id == company.id))
        assert account is not None
        account.balance = 5000
        lead = _v12_lead(
            user_id=operation.id,
            phone=phone,
            status=LeadV12Status.READY_DISPATCH.value,
        )
        db.add(lead)
        db.commit()
        return lead.id, company.id


def test_candidate_api_hides_exact_points_from_operation(api_client) -> None:
    client, factory = api_client
    lead_id, company_id = _prepare_dispatch_lead(factory, phone="13900139201")

    _login(client, "operation", "Operation123!")
    response = client.get(f"/api/v1/v1.2/dispatch-pool/{lead_id}/candidates")
    assert response.status_code == 200
    candidate = next(
        item for item in response.json()["data"]["candidates"] if item["company_id"] == company_id
    )
    assert candidate["points_price"] == 100
    assert "points_balance" not in candidate
    assert "points_reserved" not in candidate
    assert "points_available" not in candidate

    client.post("/api/v1/auth/logout")
    _login(client, "admin", "Admin123!")
    response = client.get(f"/api/v1/v1.2/dispatch-pool/{lead_id}/candidates")
    candidate = next(
        item for item in response.json()["data"]["candidates"] if item["company_id"] == company_id
    )
    assert candidate["points_balance"] == 5000
    assert candidate["points_reserved"] >= 0
    assert candidate["points_available"] == (
        candidate["points_balance"] - candidate["points_reserved"]
    )


def test_concurrent_manual_dispatch_replay_has_one_business_side_effect(api_client) -> None:
    client, factory = api_client
    lead_id, company_id = _prepare_dispatch_lead(factory, phone="13900139203")
    _login(client, "operation", "Operation123!")
    payload = {
        "company_id": company_id,
        "idempotency_key": "concurrent-v12-manual-dispatch",
        "note": "concurrent idempotency regression",
    }

    def dispatch_once(_: int):
        return client.post(
            f"/api/v1/v1.2/dispatch-pool/{lead_id}/dispatch",
            json=payload,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(dispatch_once, range(8)))

    assert all(response.status_code == 200 for response in responses), [
        response.text for response in responses
    ]
    assignment_ids = {response.json()["data"]["id"] for response in responses}
    assert len(assignment_ids) == 1
    assignment_id = assignment_ids.pop()
    with factory() as db:
        assert db.scalar(
            select(func.count(Assignment.id)).where(
                Assignment.idempotency_key == payload["idempotency_key"]
            )
        ) == 1
        assert db.scalar(
            select(func.count(AssignmentEvent.id)).where(
                AssignmentEvent.assignment_id == assignment_id,
                AssignmentEvent.event_type == "V12_MANUAL_DISPATCH",
            )
        ) == 1
        assert db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.resource_id == assignment_id,
                AuditLog.action == "V12_MANUAL_DISPATCH",
            )
        ) == 1
        assert db.scalar(
            select(func.count(NotificationOutbox.id)).where(
                NotificationOutbox.event_key == f"v12:assignment:{assignment_id}:dispatched"
            )
        ) == 1


def test_unclaimed_released_assignment_does_not_unlock_phone(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        operation = db.scalar(select(User).where(User.username == "operation"))
        franchise = db.scalar(select(User).where(User.username == "franchise_demo"))
        assert company is not None and operation is not None and franchise is not None
        lead = _v12_lead(user_id=operation.id, phone="13900139202", status=LeadV12Status.READY_DISPATCH.value)
        db.add(lead)
        db.flush()
        assignment = Assignment(
            lead_id=lead.id,
            company_id=company.id,
            receiver_company_id=company.id,
            status=AssignmentStatus.RELEASED.value,
            points_price=100,
            claim_points=100,
            lead_snapshot={"phone_masked": "139****9202"},
            assigned_by=operation.id,
            assigned_at=datetime.now(timezone.utc),
            released_at=datetime.now(timezone.utc),
            release_reason="TEST_RELEASE",
            idempotency_key="privacy-released-assignment",
        )
        db.add(assignment)
        db.commit()
        assignment_id = assignment.id

    _login(client, "franchise_demo", "Franchise123!")
    response = client.get(f"/api/v1/v1.2/assignments/{assignment_id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == AssignmentStatus.RELEASED.value
    assert data["phone"] is None
    assert data["phone_masked"] == "139****9202"

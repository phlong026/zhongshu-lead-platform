from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from apps.api.src.core.enums import AssignmentStatus
from apps.api.src.core.models import Assignment, Company, Lead, PointsAccount, User
from apps.api.src.core.models_v12 import CompanyLeadCapability, CompanyServiceAreaV12
from apps.api.src.core.security import encrypt_text, fingerprint_phone, hash_phone
from apps.api.src.core.v12_enums import LeadSourceKind, LeadV12Status


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


def test_candidate_api_hides_exact_points_from_operation(api_client) -> None:
    client, factory = api_client
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
        lead = _v12_lead(user_id=operation.id, phone="13900139201", status=LeadV12Status.READY_DISPATCH.value)
        db.add(lead)
        db.commit()
        lead_id = lead.id
        company_id = company.id

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
    assert candidate["points_available"] == 5000


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

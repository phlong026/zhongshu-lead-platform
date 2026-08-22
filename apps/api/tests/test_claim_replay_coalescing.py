from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from apps.api.src.core.enums import AssignmentStatus, PointsLedgerType
from apps.api.src.core.models import (
    Assignment,
    AssignmentEvent,
    AuditLog,
    Company,
    Lead,
    PointsAccount,
    PointsLedger,
    User,
)
from apps.api.src.core.models_v12 import CompanyLeadCapability, CompanyServiceAreaV12
from apps.api.src.core.security import encrypt_text, fingerprint_phone, hash_phone
from apps.api.src.core.v12_enums import LeadSourceKind, LeadV12Status


def _login(client, username: str, password: str) -> None:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200


def _prepare_claim(factory) -> tuple[str, str]:
    with factory() as db:
        company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        operation = db.scalar(select(User).where(User.username == "operation"))
        franchise = db.scalar(select(User).where(User.username == "franchise_demo"))
        assert company is not None and operation is not None and franchise is not None

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
        account.balance = 100_000

        now = datetime.now(timezone.utc)
        lead = Lead(
            source_type=LeadSourceKind.PLATFORM_MANUAL.value,
            source_kind=LeadSourceKind.PLATFORM_MANUAL.value,
            submitter_user_id=operation.id,
            customer_name="S01 replay customer",
            phone_encrypted=encrypt_text("13900139971"),
            phone_hash=hash_phone("13900139971"),
            phone_fingerprint=fingerprint_phone("13900139971"),
            consent_confirmed=True,
            city="上海市",
            region_code="310000",
            category_code="OLD_RENOVATION",
            brand_code="ZHONGSHU",
            need_summary="S01 replay coalescing",
            status=LeadV12Status.DISPATCHED.value,
            review_status="APPROVED",
            duplicate_status="CLEAR",
            imported_at=now,
            submitted_at=now,
            raw_payload={"synthetic_data": True},
        )
        db.add(lead)
        db.flush()
        assignment = Assignment(
            lead_id=lead.id,
            company_id=company.id,
            receiver_company_id=company.id,
            status=AssignmentStatus.PENDING_CLAIM.value,
            points_price=100,
            claim_points=100,
            lead_snapshot={"synthetic_data": True},
            assigned_by=operation.id,
            assigned_at=now,
            expires_at=now + timedelta(hours=1),
            idempotency_key=f"s01-replay-{lead.id}",
        )
        db.add(assignment)
        db.flush()
        lead.current_assignment_id = assignment.id
        db.commit()
        return assignment.id, company.id


def test_concurrent_claim_replay_has_one_business_side_effect(api_client) -> None:
    client, factory = api_client
    assignment_id, company_id = _prepare_claim(factory)
    _login(client, "franchise_demo", "Franchise123!")

    def claim_once(_: int):
        return client.post(f"/api/v1/v1.2/assignments/{assignment_id}/claim")

    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(claim_once, range(20)))

    assert all(response.status_code == 200 for response in responses), [response.text for response in responses]
    assert sum(1 for response in responses if response.json()["data"]["idempotent"] is False) == 1

    with factory() as db:
        assert db.scalar(
            select(func.count(PointsLedger.id)).where(
                PointsLedger.company_id == company_id,
                PointsLedger.ledger_type == PointsLedgerType.CLAIM.value,
                PointsLedger.business_id == assignment_id,
            )
        ) == 1
        assert db.scalar(
            select(func.count(AssignmentEvent.id)).where(
                AssignmentEvent.assignment_id == assignment_id,
                AssignmentEvent.event_type == "V12_CLAIMED",
            )
        ) == 1
        assert db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.resource_id == assignment_id,
                AuditLog.action == "V12_ASSIGNMENT_CLAIM",
            )
        ) == 1

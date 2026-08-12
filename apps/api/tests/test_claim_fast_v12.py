from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from apps.api.src.core.enums import AssignmentStatus
from apps.api.src.core.models import Assignment, Company, Lead, PointsAccount, PointsLedger, User
from apps.api.src.core.models_v12 import CompanyLeadCapability, CompanyServiceAreaV12
from apps.api.src.core.security import encrypt_text, fingerprint_phone, hash_phone
from apps.api.src.core.v12_enums import LeadSourceKind, LeadV12Status
from apps.api.src.services.claim_fast_v12 import claim_assignment_fast
from apps.api.src.services.workday_calendar import WorkdayCalendarService


def _prepare(db):
    receiver = Company(code="P71-FAST", name="P71 Fast Receiver", status="ACTIVE", level_code="V1")
    db.add(receiver)
    db.flush()
    user = User(
        username="p71_fast_owner",
        display_name="P71 Fast Owner",
        status="ACTIVE",
        company_id=receiver.id,
    )
    db.add(user)
    db.flush()
    db.add_all(
        [
            CompanyLeadCapability(
                company_id=receiver.id,
                capability_code="LEAD_RECEIVER",
                active=True,
                review_status="APPROVED",
            ),
            CompanyServiceAreaV12(
                company_id=receiver.id,
                region_code="310000",
                region_level="CITY",
                is_primary_city=True,
                active=True,
                review_status="APPROVED",
            ),
            PointsAccount(company_id=receiver.id, balance=1000, version=1),
        ]
    )
    now = datetime.now(timezone.utc)
    lead = Lead(
        source_type=LeadSourceKind.PLATFORM_MANUAL.value,
        source_kind=LeadSourceKind.PLATFORM_MANUAL.value,
        submitter_user_id=user.id,
        customer_name="P71 fast customer",
        phone_encrypted=encrypt_text("13900139711"),
        phone_hash=hash_phone("13900139711"),
        phone_fingerprint=fingerprint_phone("13900139711"),
        consent_confirmed=True,
        city="上海市",
        region_code="310000",
        category_code="OLD_RENOVATION",
        brand_code="ZHONGSHU",
        need_summary="P71 fast claim",
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
        company_id=receiver.id,
        receiver_company_id=receiver.id,
        status=AssignmentStatus.PENDING_CLAIM.value,
        points_price=100,
        claim_points=100,
        lead_snapshot={"synthetic_data": True},
        assigned_by=user.id,
        assigned_at=now,
        expires_at=now + timedelta(hours=1),
        idempotency_key="p71-fast-dispatch",
    )
    db.add(assignment)
    db.flush()
    lead.current_assignment_id = assignment.id
    db.commit()
    return receiver, user, assignment


def test_fast_claim_preserves_accounting_and_deadline(db) -> None:
    receiver, user, assignment = _prepare(db)

    execution = claim_assignment_fast(
        db,
        assignment_id=assignment.id,
        company_id=receiver.id,
        claimed_by=user.id,
    )
    db.commit()
    result = execution.result

    assert execution.lead.id == assignment.lead_id
    assert result.idempotent is False
    assert result.assignment.status == AssignmentStatus.CLAIMED.value
    account = db.scalar(select(PointsAccount).where(PointsAccount.company_id == receiver.id))
    assert account is not None and account.balance == 900
    ledgers = db.scalars(
        select(PointsLedger).where(
            PointsLedger.company_id == receiver.id,
            PointsLedger.business_id == assignment.id,
        )
    ).all()
    assert len(ledgers) == 1
    assert WorkdayCalendarService(db).workdays_between(
        result.assignment.claimed_at.date(),
        result.assignment.appeal_deadline_at.date(),
    ) == 3

    replay_execution = claim_assignment_fast(
        db,
        assignment_id=assignment.id,
        company_id=receiver.id,
        claimed_by=user.id,
    )
    db.commit()
    assert replay_execution.result.idempotent is True
    assert replay_execution.lead.id == assignment.lead_id
    assert db.scalar(select(PointsAccount.balance).where(PointsAccount.company_id == receiver.id)) == 900

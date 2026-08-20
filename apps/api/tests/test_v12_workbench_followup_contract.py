from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from apps.api.src.core import models_v12 as _models_v12  # noqa: F401
from apps.api.src.core.enums import AssignmentStatus
from apps.api.src.core.models import Assignment, AuditLog, Company, FollowUp, Lead, User
from apps.api.src.core.security import encrypt_text, hash_phone
from apps.api.src.core.v12_enums import LeadV12Status
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.auth_service import create_internal_user
from apps.api.src.services.company_service import create_company


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        headers={"Host": "app.example.com"},
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}", "Host": "app.example.com"}


def _data(response):
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["code"] == "OK"
    return payload["data"]


def _seed_assignment(
    factory,
    *,
    status: str = AssignmentStatus.CLAIMED.value,
    lead_status: str = LeadV12Status.CLAIMED.value,
    phone: str = "13900139901",
) -> tuple[str, str, datetime]:
    due_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    with factory() as db:
        company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        operation = db.scalar(select(User).where(User.username == "operation"))
        assert company is not None and operation is not None
        lead = Lead(
            source_type="TEST",
            source_kind="PLATFORM_MANUAL",
            submitter_user_id=operation.id,
            customer_name="V1.2 跟进契约客户",
            phone_encrypted=encrypt_text(phone),
            phone_hash=hash_phone(phone),
            consent_confirmed=True,
            city="上海市",
            district="浦东新区",
            region_code="310000",
            category_code="OLD_RENOVATION",
            brand_code="ZHONGSHU",
            need_summary="验证加盟商工作台跟进闭环",
            status=lead_status,
            review_status="APPROVED",
            duplicate_status="CLEAR",
            raw_payload={},
        )
        db.add(lead)
        db.flush()
        assignment = Assignment(
            lead_id=lead.id,
            company_id=company.id,
            receiver_company_id=company.id,
            status=status,
            points_price=100,
            claim_points=100,
            price_version=1,
            lead_snapshot={"phone_masked": "139****9901"},
            assigned_by=operation.id,
            claimed_at=datetime.now(timezone.utc) if status != AssignmentStatus.PENDING_CLAIM.value else None,
            first_followup_due_at=due_at,
            idempotency_key=f"v12-followup-contract-{phone}",
        )
        db.add(assignment)
        db.flush()
        lead.current_assignment_id = assignment.id
        db.commit()
        return assignment.id, company.id, due_at


def _seed_other_franchise(factory) -> dict[str, str]:
    with factory() as db:
        company = create_company(
            db,
            CompanyCreateBody(
                code="OTHER-FRAN",
                name="其他加盟商",
                owner_name="其他老板",
                contact_phone="13900139999",
                level_code="V1",
            ),
        )
        create_internal_user(
            db,
            username="other_franchise",
            password="Other123!",
            display_name="其他老板",
            role_code="FRANCHISE_OWNER",
            company_id=company.id,
        )
        db.commit()
    return {"username": "other_franchise", "password": "Other123!"}


def test_v12_workbench_followup_history_is_empty_for_own_claimed_assignment(
    api_client,
    monkeypatch,
) -> None:
    client, factory = api_client
    import apps.api.src.core.legacy_guard as legacy_guard

    monkeypatch.setattr(legacy_guard.settings, "legacy_write_enabled", False)
    assignment_id, _, _ = _seed_assignment(factory)
    franchise = _login(client, "franchise_demo", "Franchise123!")

    history = _data(client.get(f"/api/v1/followups/assignments/{assignment_id}", headers=franchise))

    assert history == []


def test_v12_workbench_followup_post_appends_history_when_legacy_writes_are_disabled(
    api_client,
    monkeypatch,
) -> None:
    client, factory = api_client
    import apps.api.src.core.legacy_guard as legacy_guard

    monkeypatch.setattr(legacy_guard.settings, "legacy_write_enabled", False)
    assignment_id, _, _ = _seed_assignment(factory, phone="13900139902")
    franchise = _login(client, "franchise_demo", "Franchise123!")
    next_at = "2026-08-21T11:30:00+08:00"
    expected_next_at = "2026-08-21T03:30:00+00:00"

    created = _data(
        client.post(
            f"/api/v1/followups/assignments/{assignment_id}",
            headers=franchise,
            json={"status": "CONTACTED", "note": "已接通，约定明天复访", "next_followup_at": next_at},
        )
    )
    history = _data(client.get(f"/api/v1/followups/assignments/{assignment_id}", headers=franchise))

    assert created["assignment_id"] == assignment_id
    assert history[0]["id"] == created["id"]
    assert history[0]["status"] == "CONTACTED"
    assert history[0]["note"] == "已接通，约定明天复访"
    assert history[0]["next_followup_at"] == expected_next_at


def test_v12_workbench_followup_post_updates_assignment_lead_and_audit(
    api_client,
    monkeypatch,
) -> None:
    client, factory = api_client
    import apps.api.src.core.legacy_guard as legacy_guard

    monkeypatch.setattr(legacy_guard.settings, "legacy_write_enabled", False)
    assignment_id, _, due_at = _seed_assignment(factory, phone="13900139903")
    franchise = _login(client, "franchise_demo", "Franchise123!")

    _data(
        client.post(
            f"/api/v1/followups/assignments/{assignment_id}",
            headers=franchise,
            json={"status": "INTERESTED", "note": "客户有意向，等待设计师联系"},
        )
    )

    with factory() as db:
        assignment = db.get(Assignment, assignment_id)
        assert assignment is not None
        lead = db.get(Lead, assignment.lead_id)
        assert lead is not None
        assert assignment.status == AssignmentStatus.FOLLOWING.value
        assert assignment.first_followup_due_at == due_at.replace(tzinfo=None)
        assert lead.status == LeadV12Status.FOLLOWING.value
        assert lead.current_follow_status == "INTERESTED"
        assert db.scalar(
            select(func.count(FollowUp.id)).where(FollowUp.assignment_id == assignment_id)
        ) == 1
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "FOLLOWUP_CREATE"))
        assert audit is not None
        assert audit.company_id == assignment.company_id
        assert audit.after_json["status"] == "INTERESTED"


def test_v12_workbench_assignment_detail_exposes_refreshed_follow_status(
    api_client,
    monkeypatch,
) -> None:
    client, factory = api_client
    import apps.api.src.core.legacy_guard as legacy_guard

    monkeypatch.setattr(legacy_guard.settings, "legacy_write_enabled", False)
    assignment_id, _, _ = _seed_assignment(factory, phone="13900139904")
    franchise = _login(client, "franchise_demo", "Franchise123!")
    _data(
        client.post(
            f"/api/v1/followups/assignments/{assignment_id}",
            headers=franchise,
            json={"status": "CONTACTED", "note": "已联系，客户要求晚间回电"},
        )
    )

    detail = _data(client.get(f"/api/v1/v1.2/assignments/{assignment_id}", headers=franchise))

    assert detail["status"] == AssignmentStatus.FOLLOWING.value
    assert detail["lead_status"] == LeadV12Status.FOLLOWING.value
    assert detail["current_follow_status"] == "CONTACTED"


def test_v12_workbench_followup_denies_cross_company_access(
    api_client,
    monkeypatch,
) -> None:
    client, factory = api_client
    import apps.api.src.core.legacy_guard as legacy_guard

    monkeypatch.setattr(legacy_guard.settings, "legacy_write_enabled", False)
    assignment_id, _, _ = _seed_assignment(factory, phone="13900139905")
    other_account = _seed_other_franchise(factory)
    other = _login(client, other_account["username"], other_account["password"])

    history = client.get(f"/api/v1/followups/assignments/{assignment_id}", headers=other)
    created = client.post(
        f"/api/v1/followups/assignments/{assignment_id}",
        headers=other,
        json={"status": "CONTACTED", "note": "跨公司不允许写入"},
    )

    assert history.status_code == 403
    assert created.status_code == 403


def test_v12_workbench_followup_denies_pending_claim_assignment(
    api_client,
    monkeypatch,
) -> None:
    client, factory = api_client
    import apps.api.src.core.legacy_guard as legacy_guard

    monkeypatch.setattr(legacy_guard.settings, "legacy_write_enabled", False)
    assignment_id, _, _ = _seed_assignment(
        factory,
        status=AssignmentStatus.PENDING_CLAIM.value,
        lead_status=LeadV12Status.DISPATCHED.value,
        phone="13900139906",
    )
    franchise = _login(client, "franchise_demo", "Franchise123!")

    response = client.post(
        f"/api/v1/followups/assignments/{assignment_id}",
        headers=franchise,
        json={"status": "CONTACTED", "note": "未领取不允许跟进"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "FOLLOWUP_NOT_ALLOWED"


def test_v12_workbench_followup_requires_manage_permission(
    api_client,
    monkeypatch,
) -> None:
    client, factory = api_client
    import apps.api.src.core.legacy_guard as legacy_guard

    monkeypatch.setattr(legacy_guard.settings, "legacy_write_enabled", False)
    assignment_id, _, _ = _seed_assignment(factory, phone="13900139907")
    operation = _login(client, "operation", "Operation123!")

    response = client.post(
        f"/api/v1/followups/assignments/{assignment_id}",
        headers=operation,
        json={"status": "CONTACTED", "note": "运营角色没有加盟商跟进权限"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"

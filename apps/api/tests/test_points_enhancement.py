from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from apps.api.src.core.models import Company, Notification, NotificationOutbox, PointsPackage
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.auth_service import create_internal_user
from apps.api.src.services.company_service import create_company
from apps.api.src.services.points_service import (
    account_summary,
    change_points,
    reconcile_points_account,
    run_low_points_warnings,
)


def test_level_entitlements_are_exposed_in_account_summary(db):
    company = create_company(db, CompanyCreateBody(code="P101", name="积分权益公司", level_code="V2"))
    db.add(
        PointsPackage(
            code="V2_PACKAGE",
            name="V2 档位",
            cash_amount_cents=5_000_000,
            base_points=50_000,
            bonus_points=5_000,
            level_code="V2",
            entitlements_json={"客资折扣": "95折", "服务优先级": "优先"},
            version=2,
            status="PUBLISHED",
            effective_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    db.commit()

    result = account_summary(db, company.id)
    assert result["level_code"] == "V2"
    assert result["level_entitlements"]["客资折扣"] == "95折"
    assert result["level_package"]["version"] == 2
    assert result["low_points"] is True


def test_low_points_warning_is_deduplicated_per_company_per_day(db, monkeypatch):
    import apps.api.src.services.points_service as module

    monkeypatch.setattr(module.settings, "low_points_warning_threshold", 1000)
    company = create_company(db, CompanyCreateBody(code="P102", name="低积分公司"))
    user = create_internal_user(
        db,
        username="low-points-owner",
        password="Owner123!",
        display_name="低积分老板",
        role_code="FRANCHISE_OWNER",
        company_id=company.id,
    )
    company.primary_user_id = user.id
    change_points(
        db,
        company_id=company.id,
        delta=500,
        ledger_type="ADJUST",
        business_type="TEST",
        business_id="seed",
        idempotency_key="seed-low-points",
        created_by=None,
    )
    db.commit()

    day_one = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    first = run_low_points_warnings(db, as_of=day_one)
    repeated_same_day = run_low_points_warnings(db, as_of=day_one + timedelta(hours=6))
    db.commit()
    assert first["warned"] == 1
    assert repeated_same_day["warned"] == 0
    assert db.scalar(select(Notification).where(Notification.company_id == company.id, Notification.scene == "LOW_POINTS"))
    assert db.scalar(select(NotificationOutbox).where(NotificationOutbox.aggregate_type == "points_account"))

    change_points(
        db,
        company_id=company.id,
        delta=1000,
        ledger_type="ADJUST",
        business_type="TEST",
        business_id="recover",
        idempotency_key="recover-points",
        created_by=None,
    )
    db.commit()
    recovered = run_low_points_warnings(db, as_of=day_one + timedelta(days=1))
    assert recovered["warned"] == 0

    change_points(
        db,
        company_id=company.id,
        delta=-700,
        ledger_type="CLAIM",
        business_type="TEST",
        business_id="new-crossing",
        idempotency_key="new-low-crossing",
        created_by=None,
    )
    next_day = run_low_points_warnings(db, as_of=day_one + timedelta(days=2))
    db.commit()
    assert next_day["warned"] == 1
    assert len(db.scalars(select(Notification).where(Notification.company_id == company.id, Notification.scene == "LOW_POINTS")).all()) == 2


def test_points_reconciliation_detects_balanced_ledger(db):
    company = create_company(db, CompanyCreateBody(code="P103", name="积分对账公司"))
    change_points(db, company_id=company.id, delta=2000, ledger_type="RECHARGE", business_type="TEST", business_id="r1", idempotency_key="recon-r1", created_by=None)
    change_points(db, company_id=company.id, delta=-300, ledger_type="CLAIM", business_type="TEST", business_id="c1", idempotency_key="recon-c1", created_by=None)
    db.commit()

    result = reconcile_points_account(db, company.id)
    assert result["balanced"] is True
    assert result["expected_closing_balance"] == 1700
    assert result["snapshot_balance"] == 1700
    assert result["difference"] == 0
    assert result["sequence_error_count"] == 0


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    assert "token" not in response.json()["data"]
    return {"Authorization": f"Bearer {token}"}


def test_manual_recharge_requires_explicit_confirmation_and_enqueues_notice(api_client):
    client, factory = api_client
    admin = _login(client, "admin", "Admin123!")
    packages = client.get("/api/v1/points/packages", headers=admin).json()["data"]
    package = packages[0]
    with factory() as db:
        company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        assert company
        company_id = company.id

    payload = {
        "company_id": company_id,
        "package_id": package["id"],
        "external_reference": "BANK-P101-CONFIRM",
        "cash_amount_cents": package["cash_amount_cents"],
        "idempotency_key": "recharge-p101-confirm",
    }
    rejected = client.post("/api/v1/points/recharge", headers=admin, json=payload)
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "POINTS_RECHARGE_CONFIRM_REQUIRED"

    accepted = client.post("/api/v1/points/recharge", headers=admin, json={**payload, "confirmed": True})
    assert accepted.status_code == 200, accepted.text
    first_ledger = accepted.json()["data"]
    assert first_ledger["delta"] == package["total_points"]

    repeated = client.post("/api/v1/points/recharge", headers=admin, json={**payload, "confirmed": True})
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["data"]["id"] == first_ledger["id"]

    with factory() as db:
        notifications = db.scalars(select(Notification).where(Notification.company_id == company_id, Notification.scene == "POINTS_RECHARGED")).all()
        outbox = db.scalars(select(NotificationOutbox).where(NotificationOutbox.event_type == "POINTS_RECHARGED")).all()
        assert len(notifications) == 1
        assert len(outbox) == 1


def test_publishing_new_package_version_closes_previous_active_version(api_client):
    client, factory = api_client
    admin = _login(client, "admin", "Admin123!")
    payload = {
        "code": "V2_VERSIONED",
        "name": "V2版本档",
        "cash_amount_cents": 2_000_000,
        "base_points": 20_000,
        "bonus_points": 2_000,
        "level_code": "V2",
        "entitlements": {"服务优先级": "优先"},
        "publish": True,
    }
    first = client.post("/api/v1/points/packages", headers=admin, json=payload)
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/points/packages",
        headers=admin,
        json={**payload, "name": "V2版本档升级", "bonus_points": 3_000},
    )
    assert second.status_code == 200, second.text
    assert second.json()["data"]["version"] == 2

    with factory() as db:
        versions = db.scalars(
            select(PointsPackage)
            .where(PointsPackage.code == "V2_VERSIONED")
            .order_by(PointsPackage.version)
        ).all()
        assert len(versions) == 2
        assert versions[0].expires_at is not None
        assert versions[1].expires_at is None

    active = client.get("/api/v1/points/packages", headers=admin).json()["data"]
    active_versions = [item for item in active if item["code"] == "V2_VERSIONED"]
    assert len(active_versions) == 1
    assert active_versions[0]["version"] == 2

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import event, func, select

from apps.api.src.core.models import (
    Assignment,
    AuditLog,
    Company,
    FollowUp,
    Lead,
    PointsAccount,
    PointsLedger,
    ReturnRequest,
    User,
)
from apps.api.src.core.models_v12 import SupplierLeadReward
from apps.api.src.services.points_service import reverse_ledger


def login(client, username: str, password: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    client.headers.update({"Authorization": f"Bearer {token}"})


def _contains_key(value, names: set[str]) -> bool:
    if isinstance(value, dict):
        return any(key in names or _contains_key(item, names) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_key(item, names) for item in value)
    return False


def test_superadmin_can_read_v12_overview_and_audit(api_client):
    client, _factory = api_client
    login(client, "admin", "Admin123!")

    report = client.get("/api/v1/v1.2/reports/overview")
    assert report.status_code == 200, report.text
    data = report.json()["data"]
    assert {"leads", "assignments", "returns", "supplier_rewards", "points_ledger"} <= set(data)

    audit = client.get("/api/v1/v1.2/audit-events?page=1&page_size=20")
    assert audit.status_code == 200, audit.text
    assert {"items", "total", "page", "page_size"} <= set(audit.json()["data"])


def test_superadmin_can_read_management_and_finance_decision_dashboards(api_client):
    client, _factory = api_client
    login(client, "admin", "Admin123!")

    management = client.get("/api/v1/v1.2/reports/management-dashboard?days=30")
    assert management.status_code == 200, management.text
    data = management.json()["data"]
    assert {
        "new_leads",
        "pending_verification",
        "ready_dispatch",
        "claimed",
        "effective_completion_rate",
        "returned_exceptions",
        "pending_reward_settlement",
    } <= set(data["kpis"])
    assert {"trend", "funnel", "source_distribution", "region_distribution", "provider_distribution", "exceptions"} <= set(data)

    with _factory() as db:
        company = Company(code="FINANCE-DASHBOARD", name="充值看板测试加盟商", status="ACTIVE")
        db.add(company)
        db.flush()
        account = PointsAccount(company_id=company.id, balance=345)
        db.add(account)
        db.flush()
        db.add(
            PointsLedger(
                account_id=account.id,
                company_id=company.id,
                ledger_type="RECHARGE",
                delta=500,
                balance_after=345,
                business_type="TEST",
                business_id="finance-dashboard",
                idempotency_key="finance-dashboard-recharge",
                external_reference="TEST-FINANCE-RECHARGE",
            )
        )
        db.commit()

    finance = client.get("/api/v1/v1.2/reports/finance-dashboard?days=30")
    assert finance.status_code == 200, finance.text
    finance_data = finance.json()["data"]
    assert {"pending_settlement", "settled", "disputed", "voided"} <= set(finance_data["summary"])
    assert {"trend", "source_ranking", "details"} <= set(finance_data)
    assert {"period_recharged_points", "period_recharge_count", "total_recharged_points", "total_recharge_count", "remaining_points"} <= set(finance_data["recharge_summary"])
    assert {"trend", "recent_records"} <= set(finance_data["recharge"])
    assert finance_data["recharge_summary"]["period_recharged_points"] >= 500
    assert finance_data["recharge_summary"]["total_recharge_count"] >= 1
    assert finance_data["recharge_summary"]["remaining_points"] >= 345
    assert any(record["external_reference"] == "TEST-FINANCE-RECHARGE" for record in finance_data["recharge"]["recent_records"])


def _dashboard_lead(*, name: str, created_at: datetime, status: str = "READY_DISPATCH") -> Lead:
    return Lead(
        source_type="H5",
        source_kind="SUPPLIER_H5",
        customer_name=name,
        phone_encrypted=f"encrypted-{name}",
        phone_hash=f"hash-{name}",
        status=status,
        created_at=created_at,
        updated_at=created_at,
    )


def test_management_dashboard_uses_each_new_lead_cohort_for_effective_rate(api_client) -> None:
    client, factory = api_client
    login(client, "admin", "Admin123!")
    cohort_at = datetime.now(timezone.utc) - timedelta(days=20)

    with factory() as db:
        company = db.scalar(select(Company).where(Company.status == "ACTIVE"))
        actor = db.scalar(select(User).where(User.username == "admin"))
        assert company is not None and actor is not None

        completed_lead = _dashboard_lead(name="同批已完成", created_at=cohort_at)
        pending_lead = _dashboard_lead(
            name="同批待审核",
            created_at=cohort_at,
            status="PENDING_REVIEW",
        )
        old_lead_one = _dashboard_lead(
            name="旧批次一",
            created_at=cohort_at - timedelta(days=60),
        )
        old_lead_two = _dashboard_lead(
            name="旧批次二",
            created_at=cohort_at - timedelta(days=61),
        )
        db.add_all([completed_lead, pending_lead, old_lead_one, old_lead_two])
        db.flush()

        completed_assignment = Assignment(
            lead_id=completed_lead.id,
            company_id=company.id,
            status="COMPLETED",
            points_price=100,
            assigned_by=actor.id,
        )
        old_assignments = [
            Assignment(
                lead_id=lead.id,
                company_id=company.id,
                status="FOLLOWING",
                points_price=100,
                assigned_by=actor.id,
            )
            for lead in (old_lead_one, old_lead_two)
        ]
        db.add_all([completed_assignment, *old_assignments])
        db.flush()
        db.add_all(
            [
                FollowUp(
                    assignment_id=assignment.id,
                    company_id=company.id,
                    status="DEAL",
                    created_by=actor.id,
                    created_at=cohort_at,
                )
                for assignment in old_assignments
            ]
        )
        expected_pending = int(
            db.scalar(
                select(func.count(Lead.id)).where(
                    Lead.source_kind.is_not(None),
                    Lead.status.in_(
                        (
                            "PENDING_REVIEW",
                            "PENDING_TELESALES_VERIFY",
                            "PENDING_OPERATION_DISPOSITION",
                        )
                    ),
                )
            )
            or 0
        )
        db.commit()

    response = client.get("/api/v1/v1.2/reports/management-dashboard?days=30")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    cohort = next(item for item in data["trend"] if item["date"] == cohort_at.date().isoformat())
    assert cohort == {
        "date": cohort_at.date().isoformat(),
        "new_leads": 2,
        "effective_completed": 1,
        "effective_rate": 50.0,
    }
    assert data["kpis"]["pending_verification"] == expected_pending


def test_decision_dashboards_do_not_materialize_unbounded_business_entities(api_client) -> None:
    client, _factory = api_client
    login(client, "admin", "Admin123!")
    loaded: list[str] = []
    tracked = (Lead, Assignment, ReturnRequest, SupplierLeadReward, PointsLedger)

    def remember_loaded(target, _context) -> None:
        loaded.append(type(target).__name__)

    for model in tracked:
        event.listen(model, "load", remember_loaded)
    try:
        management = client.get("/api/v1/v1.2/reports/management-dashboard?days=30")
        finance = client.get("/api/v1/v1.2/reports/finance-dashboard?days=30")
    finally:
        for model in tracked:
            event.remove(model, "load", remember_loaded)

    assert management.status_code == 200, management.text
    assert finance.status_code == 200, finance.text
    assert loaded == []


def test_finance_dashboard_nets_reversed_recharges_and_marks_recent_record(api_client) -> None:
    client, factory = api_client
    login(client, "admin", "Admin123!")
    before = client.get("/api/v1/v1.2/reports/finance-dashboard?days=30")
    assert before.status_code == 200, before.text
    baseline = before.json()["data"]["recharge_summary"]

    with factory() as db:
        actor = db.scalar(select(User).where(User.username == "admin"))
        assert actor is not None
        company = Company(code="REVERSED-DASHBOARD", name="冲正看板测试加盟商", status="ACTIVE")
        db.add(company)
        db.flush()
        account = PointsAccount(company_id=company.id, balance=500)
        db.add(account)
        db.flush()
        recharge = PointsLedger(
            account_id=account.id,
            company_id=company.id,
            ledger_type="RECHARGE",
            delta=500,
            balance_after=500,
            business_type="TEST",
            business_id="reversed-finance-dashboard",
            idempotency_key="reversed-finance-dashboard-recharge",
            external_reference="TEST-FINANCE-REVERSED",
        )
        db.add(recharge)
        db.flush()
        reverse_ledger(
            db,
            recharge,
            reason="看板冲正口径回归测试",
            idempotency_key="reversed-finance-dashboard-reversal",
            created_by=actor.id,
        )
        db.commit()

    response = client.get("/api/v1/v1.2/reports/finance-dashboard?days=30")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    summary = data["recharge_summary"]
    assert summary["period_recharged_points"] == baseline["period_recharged_points"]
    assert summary["period_recharge_count"] == baseline["period_recharge_count"]
    assert summary["total_recharged_points"] == baseline["total_recharged_points"]
    assert summary["total_recharge_count"] == baseline["total_recharge_count"]
    record = next(
        item
        for item in data["recharge"]["recent_records"]
        if item["external_reference"] == "TEST-FINANCE-REVERSED"
    )
    assert record["original_points"] == 500
    assert record["points"] == 0
    assert record["reversed"] is True
    assert record["reversed_at"]


def test_operation_can_read_report_and_audit_after_sprint5_rbac(api_client):
    client, _factory = api_client
    login(client, "operation", "Operation123!")

    assert client.get("/api/v1/v1.2/reports/overview").status_code == 200
    assert client.get("/api/v1/v1.2/audit-events").status_code == 200


def test_audit_events_expose_the_business_operator_name(api_client):
    client, _factory = api_client
    login(client, "operation", "Operation123!")

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    display_name = me.json()["data"]["display_name"]
    response = client.get("/api/v1/v1.2/audit-events?page=1&page_size=50")

    assert response.status_code == 200, response.text
    events = response.json()["data"]["items"]
    own_login = next(item for item in events if item["action"] == "AUTH_LOGIN")
    assert own_login["actor_name"] == display_name


def test_operation_overview_hides_financial_projection(api_client):
    client, _factory = api_client
    login(client, "operation", "Operation123!")

    response = client.get("/api/v1/v1.2/reports/overview")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert "points_ledger" not in data
    assert not _contains_key(data, {"net_delta", "balance", "recharge", "income", "revenue"})


def test_superadmin_overview_keeps_points_ledger_projection(api_client):
    client, _factory = api_client
    login(client, "admin", "Admin123!")

    response = client.get("/api/v1/v1.2/reports/overview")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert {"count", "net_delta"} <= set(data["points_ledger"])


def test_management_overview_exposes_business_pool_verification_and_risk_counts(api_client):
    client, _factory = api_client
    login(client, "admin", "Admin123!")

    response = client.get("/api/v1/v1.2/reports/overview")

    assert response.status_code == 200, response.text
    management = response.json()["data"]["management"]
    assert {"lead_pool", "verification", "exceptions"} <= set(management)
    assert {"total", "unassigned", "dispatching", "problem"} <= set(management["lead_pool"])
    assert {"pending", "in_progress", "awaiting_operation", "overdue"} <= set(management["verification"])


def test_operation_can_update_a_franchise_company_profile(api_client):
    client, _factory = api_client
    login(client, "operation", "Operation123!")

    companies = client.get("/api/v1/companies?page=1&page_size=1")
    assert companies.status_code == 200, companies.text
    company = companies.json()["data"]["items"][0]

    response = client.patch(
        f"/api/v1/companies/{company['id']}",
        json={"owner_name": "运营更新负责人"},
    )

    assert response.status_code == 200, response.text


def test_platform_user_can_change_own_password_and_keep_current_session(api_client):
    client, _factory = api_client
    login(client, "operation", "Operation123!")

    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Operation123!", "new_password": "Operation456!"},
    )

    assert response.status_code == 200, response.text
    client.headers.pop("Authorization", None)
    assert client.get("/api/v1/auth/me").status_code == 200

    old_password_login = client.post(
        "/api/v1/auth/login",
        json={"username": "operation", "password": "Operation123!"},
    )
    assert old_password_login.status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "operation", "password": "Operation456!"},
    ).status_code == 200


def test_platform_user_can_change_own_username_and_keep_current_session(api_client):
    client, factory = api_client
    login(client, "operation", "Operation123!")

    response = client.post(
        "/api/v1/auth/change-username",
        json={"current_password": "Operation123!", "username": "operation-renamed"},
    )

    assert response.status_code == 200, response.text
    client.headers.pop("Authorization", None)
    assert client.get("/api/v1/auth/me").json()["data"]["username"] == "operation-renamed"
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "operation", "password": "Operation123!"},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "operation-renamed", "password": "Operation123!"},
    ).status_code == 200

    with factory() as db:
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "AUTH_USERNAME_CHANGE").order_by(AuditLog.created_at.desc())
        )
        assert audit is not None
        assert audit.before_json == {"username": "operation"}
        assert audit.after_json == {"username": "operation-renamed"}


def test_franchise_has_company_report_but_not_platform_overview(api_client):
    client, _factory = api_client
    login(client, "franchise_demo", "Franchise123!")

    own = client.get("/api/v1/v1.2/reports/own")
    assert own.status_code == 200, own.text
    assert own.json()["data"]["company_id"]

    overview = client.get("/api/v1/v1.2/reports/overview")
    assert overview.status_code == 403


def test_trace_returns_not_found_for_unknown_business_id(api_client):
    client, _factory = api_client
    login(client, "admin", "Admin123!")
    response = client.get("/api/v1/v1.2/trace/unknown-business-id")
    assert response.status_code == 404
    assert response.json()["code"] == "BUSINESS_TRACE_NOT_FOUND"

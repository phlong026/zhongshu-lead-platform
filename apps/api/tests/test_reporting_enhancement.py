from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import event

from apps.api.src.core.auth import Principal
from apps.api.src.core.models import Assignment, Company, FollowUp, Lead, PointsAccount, PointsLedger
from apps.api.src.services.admin_service import dashboard_performance, dashboard_summary
from apps.api.src.services.auth_service import create_internal_user


def principal(*permissions: str, roles: tuple[str, ...] = ("OWNER",)) -> Principal:
    return Principal(
        user_id="report-user",
        display_name="报表测试",
        company_id=None,
        role_codes=frozenset(roles),
        permission_codes=frozenset(permissions),
        session_version=1,
    )


def _seed_reporting_data(db):
    company = Company(code="RPT-C1", name="报表加盟商", status="ACTIVE")
    db.add(company)
    db.flush()
    operator = create_internal_user(
        db,
        username="report-operator",
        password="Report123!",
        display_name="报表运营",
        role_code="OPERATION",
    )
    lead = Lead(
        customer_name="上海客户",
        phone_encrypted="encrypted",
        phone_hash="report-hash",
        city="上海市",
        region_code="310000",
        source_channel="视频号",
        status="QUALIFIED",
    )
    db.add(lead)
    db.flush()
    assignment = Assignment(
        lead_id=lead.id,
        company_id=company.id,
        status="COMPLETED",
        points_price=100,
        lead_snapshot={},
        assigned_by=operator.id,
        claimed_at=datetime.now(timezone.utc),
    )
    db.add(assignment)
    db.flush()
    db.add(FollowUp(assignment_id=assignment.id, company_id=company.id, status="COMPLETED", note="成交", created_by=operator.id))
    account = PointsAccount(company_id=company.id, balance=1200)
    db.add(account)
    db.flush()
    db.add_all(
        [
            PointsLedger(account_id=account.id, company_id=company.id, ledger_type="RECHARGE", delta=2000, balance_after=2000, business_type="TEST", business_id="r", idempotency_key="report-r"),
            PointsLedger(account_id=account.id, company_id=company.id, ledger_type="CLAIM", delta=-1000, balance_after=1000, business_type="TEST", business_id="c", idempotency_key="report-c"),
            PointsLedger(account_id=account.id, company_id=company.id, ledger_type="RETURN", delta=200, balance_after=1200, business_type="TEST", business_id="x", idempotency_key="report-x"),
        ]
    )
    db.commit()


def test_performance_report_exposes_funnel_regions_and_role_sensitive_finance(db):
    _seed_reporting_data(db)
    operation = dashboard_performance(db, principal("dashboard.operation.read", roles=("OPERATION",)), days=30)
    assert operation["funnel"]["leads_created"] == 1
    assert operation["funnel"]["assignments"] == 1
    assert operation["funnel"]["claim_rate"] == 100.0
    assert operation["funnel"]["followup_rate"] == 100.0
    assert operation["regions"][0]["region"] == "上海市"
    assert "finance" not in operation

    owner = dashboard_performance(db, principal("dashboard.finance.read", "points.read"), days=30)
    assert owner["finance"]["points_recharged"] == 2000
    assert owner["finance"]["points_consumed"] == 1000
    assert owner["finance"]["points_refunded"] == 200
    assert owner["finance"]["net_points_change"] == 1200


def test_dashboard_summary_adds_claim_followup_and_conversion_rates_without_finance_leak(db):
    _seed_reporting_data(db)
    operation = dashboard_summary(db, principal("dashboard.operation.read", roles=("OPERATION",)))
    assert operation["business"]["claim_rate"] == 100.0
    assert operation["business"]["followup_rate"] == 100.0
    assert operation["business"]["conversion_rate"] == 100.0
    assert "finance" not in operation


def test_performance_report_uses_three_bounded_aggregate_queries(db):
    _seed_reporting_data(db)
    statements: list[str] = []

    def record_statement(*args) -> None:
        statements.append(args[2])

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        report = dashboard_performance(
            db,
            principal("dashboard.finance.read", "points.read"),
            days=30,
        )
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert report["funnel"]["leads_created"] == 1
    assert report["finance"]["net_points_change"] == 1200
    assert len(statements) == 3

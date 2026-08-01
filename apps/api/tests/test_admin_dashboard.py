from __future__ import annotations

from apps.api.src.core.auth import Principal
from apps.api.src.core.models import AuditLog, Company, Lead, PointsAccount, PointsLedger, SystemConfig
from apps.api.src.services.admin_service import dashboard_summary, dashboard_trends, operational_alerts
from apps.api.src.services.company_service import company_to_dict
from apps.api.src.core.security import encrypt_text


def principal(*permissions: str, roles: tuple[str, ...] = ("OWNER",), company_id: str | None = None) -> Principal:
    return Principal(
        user_id="u1",
        display_name="测试用户",
        company_id=company_id,
        role_codes=frozenset(roles),
        permission_codes=frozenset(permissions),
        session_version=1,
    )


def test_dashboard_finance_is_role_sensitive(db):
    company = Company(code="C1", name="加盟商一", status="ACTIVE")
    db.add(company)
    db.flush()
    account = PointsAccount(company_id=company.id, balance=5000)
    db.add(account)
    db.flush()
    db.add(
        PointsLedger(
            account_id=account.id,
            company_id=company.id,
            ledger_type="RECHARGE",
            delta=5000,
            balance_after=5000,
            business_type="TEST",
            business_id="x",
            idempotency_key="test-recharge",
        )
    )
    db.add(Lead(customer_name="张先生", phone_encrypted="x", phone_hash="h", status="QUALIFIED"))
    db.commit()

    operation_data = dashboard_summary(db, principal("dashboard.operation.read", roles=("OPERATION",)))
    assert "finance" not in operation_data
    assert operation_data["business"]["qualified"] == 1

    owner_data = dashboard_summary(db, principal("dashboard.finance.read", "points.read"))
    assert owner_data["finance"]["points_balance_total"] == 5000
    assert owner_data["finance"]["points_recharged_total"] == 5000


def test_company_masked_phone_uses_encrypted_contact(db):
    company = Company(code="C2", name="加盟商二", contact_phone_encrypted=encrypt_text("13812345678"))
    db.add(company)
    db.flush()
    data = company_to_dict(company)
    assert data["contact_phone_masked"] == "138****5678"


def test_dashboard_trends_and_alerts(db):
    db.add(Lead(customer_name="王先生", phone_encrypted="x", phone_hash="h2", status="IMPORT_ERROR"))
    db.commit()
    trends = dashboard_trends(db, days=3)
    assert len(trends["labels"]) == 3
    assert sum(trends["series"]["leads"]) == 1
    alerts = operational_alerts(db)
    assert alerts["import_errors"] == 1

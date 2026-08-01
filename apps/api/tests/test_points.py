import pytest
from sqlalchemy import select

from apps.api.src.core.errors import AppError
from apps.api.src.core.models import Company, PointsLedger, PointsPackage
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.company_service import create_company
from apps.api.src.services.points_service import change_points, recharge_points, reverse_ledger


def test_recharge_debit_and_reversal(db) -> None:
    company = create_company(db, CompanyCreateBody(code="C001", name="测试公司"))
    package = PointsPackage(code="P20K", name="2万档", cash_amount_cents=2_000_000, base_points=20_000, bonus_points=1000, level_code="V1", version=1, status="PUBLISHED")
    db.add(package)
    db.commit()
    recharge = recharge_points(db, company_id=company.id, package=package, cash_amount_cents=2_000_000, external_reference="BANK-001", idempotency_key="recharge-0001", created_by=None, note=None)
    debit = change_points(db, company_id=company.id, delta=-100, ledger_type="CLAIM", business_type="ASSIGNMENT", business_id="a1", idempotency_key="claim-0001", created_by=None)
    reversal = reverse_ledger(db, debit, reason="测试冲正", idempotency_key="reverse-0001", created_by="u1")
    db.commit()
    assert recharge.balance_after == 21_000
    assert debit.balance_after == 20_900
    assert reversal.balance_after == 21_000


def test_insufficient_points_is_rejected(db) -> None:
    company = create_company(db, CompanyCreateBody(code="C002", name="积分不足公司"))
    db.commit()
    with pytest.raises(AppError) as exc:
        change_points(db, company_id=company.id, delta=-1, ledger_type="CLAIM", business_type="ASSIGNMENT", business_id="a", idempotency_key="claim-x001", created_by=None)
    assert exc.value.code == "POINTS_INSUFFICIENT"

import pytest
from sqlalchemy import select

from apps.api.src.core.auth import Principal
from apps.api.src.core.errors import AppError
from apps.api.src.core.models import Assignment, Lead, LeadPriceRule
from apps.api.src.core.security import encrypt_text, hash_phone
from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.company_service import create_company
from apps.api.src.services.dispatch_service import candidate_companies, dispatch_lead
from apps.api.src.services.points_service import change_points


def operation_principal() -> Principal:
    return Principal(user_id="op-user", display_name="运营", company_id=None, role_codes=frozenset({"OPERATION"}), permission_codes=frozenset({"lead.dispatch","assignment.read"}), session_version=1)


def test_candidate_and_single_active_dispatch(db) -> None:
    company = create_company(db, CompanyCreateBody(code="SH-A", name="上海旧改加盟商", region_codes=["310100"], capabilities=[{"category_code":"OLD_RENOVATION","brand_code":None}]))
    company.primary_user_id = "wechat-user"
    lead = Lead(customer_name="张先生", phone_encrypted=encrypt_text("13800138000"), phone_hash=hash_phone("13800138000"), city="上海市", region_code="310100", category_code="OLD_RENOVATION", status="QUALIFIED")
    db.add(lead)
    db.add(LeadPriceRule(region_code="310100", category_code="OLD_RENOVATION", points_cost=150, priority=1, version=1, status="PUBLISHED"))
    db.flush()
    change_points(db, company_id=company.id, delta=1000, ledger_type="ADJUST", business_type="TEST", business_id="seed", idempotency_key="seed-points-01", created_by=None)
    db.commit()
    items = candidate_companies(db, lead)
    assert items[0]["eligible"] is True
    assignment = dispatch_lead(db, lead_id=lead.id, company_id=company.id, principal=operation_principal(), idempotency_key="dispatch-0001")
    db.commit()
    assert assignment.status == "PENDING_CLAIM"
    assert db.get(Lead, lead.id).current_assignment_id == assignment.id
    with pytest.raises(AppError):
        dispatch_lead(db, lead_id=lead.id, company_id=company.id, principal=operation_principal(), idempotency_key="dispatch-0002")

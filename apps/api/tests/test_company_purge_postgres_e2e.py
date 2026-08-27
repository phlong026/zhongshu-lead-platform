from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.core import reward_models_v12 as _reward_models_v12  # noqa: F401
from apps.api.src.core.models import (
    Assignment,
    Company,
    Lead,
    PointsAccount,
    PointsLedger,
    ReturnRequest,
    User,
)
from apps.api.src.core.models_v12 import SupplierLeadReward
from apps.api.src.services.company_service import delete_test_company


def test_postgres_purges_self_contained_test_company_with_finance_history() -> None:
    database_url = os.environ.get("V12_E2E_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("requires the disposable V12 E2E PostgreSQL database")

    engine = create_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.skip("PostgreSQL foreign-key purge coverage only")
    if "companies" not in inspect(engine).get_table_names():
        engine.dispose()
        pytest.skip("database schema not initialized; run scripts/run_v12_e2e.py")

    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    suffix = uuid4().hex[:10]
    company_id = ""
    try:
        with factory() as db:
            operator = User(
                username=f"purge_operator_{suffix}",
                display_name="PostgreSQL 清理测试员",
                status="ACTIVE",
            )
            company = Company(
                code=f"PG-PURGE-{suffix}",
                name=f"PostgreSQL 清理测试主体 {suffix}",
                status="DISABLED",
                is_test=True,
            )
            db.add_all([operator, company])
            db.flush()
            company_id = company.id
            account = PointsAccount(company_id=company.id, balance=70, version=1)
            lead = Lead(
                customer_name="PostgreSQL 测试客户",
                phone_encrypted="test-encrypted-phone",
                phone_hash=f"pg-purge-phone-{suffix}",
                status="CLAIMED",
                source_kind="SUPPLIER_H5",
                supplier_company_id=company.id,
            )
            db.add_all([account, lead])
            db.flush()
            assignment = Assignment(
                lead_id=lead.id,
                company_id=company.id,
                supplier_company_id=company.id,
                receiver_company_id=company.id,
                status="CLAIMED",
                points_price=100,
                claim_points=100,
                lead_snapshot={},
                assigned_by=operator.id,
            )
            db.add(assignment)
            db.flush()
            db.add(
                ReturnRequest(
                    assignment_id=assignment.id,
                    lead_id=lead.id,
                    company_id=company.id,
                    reason_code="TEST_RETURN",
                    reason_version=1,
                    description="PostgreSQL 测试退回",
                    status="DRAFT",
                    submitted_by=operator.id,
                )
            )
            db.add(
                SupplierLeadReward(
                    lead_id=lead.id,
                    assignment_id=assignment.id,
                    supplier_company_id=company.id,
                    receiver_company_id=company.id,
                    status="OBSERVING",
                    claim_points=100,
                    reward_ratio_bps=3000,
                    reward_points=30,
                    rule_version=1,
                    rule_snapshot_json={"version": 1, "ratio_bps": 3000},
                )
            )
            db.add(
                PointsLedger(
                    account_id=account.id,
                    company_id=company.id,
                    ledger_type="RECHARGE",
                    delta=70,
                    balance_after=70,
                    business_type="RECHARGE",
                    business_id=f"pg-purge-{suffix}",
                    idempotency_key=f"pg-purge-{suffix}",
                )
            )
            db.commit()

        with factory() as db:
            snapshot = delete_test_company(
                db,
                company_id,
                confirm_name=f"PostgreSQL 清理测试主体 {suffix}",
            )
            db.commit()
            assert snapshot["purged"]["points_ledgers"] == 1

        with factory() as db:
            assert db.get(Company, company_id) is None
            assert db.scalar(
                select(PointsLedger).where(PointsLedger.company_id == company_id)
            ) is None
            assert db.scalar(
                select(PointsAccount).where(PointsAccount.company_id == company_id)
            ) is None
    finally:
        engine.dispose()

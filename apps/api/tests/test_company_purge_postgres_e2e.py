from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
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
    VerificationTask,
)
from apps.api.src.core.models_v12 import (
    CompanyLeadCapability,
    CompanyServiceAreaV12,
    SupplierLeadReward,
)
from apps.api.src.core.security import encrypt_text
from apps.api.src.core.errors import AppError
from apps.api.src.services.company_service import delete_test_company
from apps.api.src.services.dispatch_v12 import claim_assignment
from apps.api.src.services.supplier_reward_v12 import settle_supplier_reward


def _postgres_factory():
    database_url = os.environ.get("V12_E2E_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("requires the disposable V12 E2E PostgreSQL database")
    engine = create_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.skip("PostgreSQL concurrency coverage only")
    if "companies" not in inspect(engine).get_table_names():
        engine.dispose()
        pytest.skip("database schema not initialized; run scripts/run_v12_e2e.py")
    return engine, sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


def test_postgres_purges_self_contained_test_company_with_finance_history() -> None:
    engine, factory = _postgres_factory()
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


def test_postgres_purge_retries_after_concurrent_claim_and_removes_finance_rows() -> None:
    engine, factory = _postgres_factory()
    suffix = uuid4().hex[:10]
    writer_ready = Event()
    allow_commit = Event()
    try:
        with factory() as db:
            operator = User(
                username=f"purge_claim_operator_{suffix}",
                display_name="并发认领测试员",
                status="ACTIVE",
            )
            test_supplier = Company(
                code=f"PG-CLAIM-TEST-{suffix}",
                name=f"并发认领测试主体 {suffix}",
                status="DISABLED",
                is_test=True,
            )
            receiver = Company(
                code=f"PG-CLAIM-RECV-{suffix}",
                name=f"并发认领真实接收方 {suffix}",
                status="ACTIVE",
                is_test=False,
            )
            db.add_all([operator, test_supplier, receiver])
            db.flush()
            claimant = User(
                username=f"purge_claimant_{suffix}",
                display_name="并发认领人",
                status="ACTIVE",
                company_id=receiver.id,
            )
            receiver_account = PointsAccount(
                company_id=receiver.id,
                balance=200,
                version=1,
            )
            test_account = PointsAccount(
                company_id=test_supplier.id,
                balance=0,
                version=1,
            )
            db.add_all(
                [
                    claimant,
                    receiver_account,
                    test_account,
                    CompanyLeadCapability(
                        company_id=receiver.id,
                        capability_code="LEAD_RECEIVER",
                        active=True,
                        review_status="APPROVED",
                    ),
                    CompanyServiceAreaV12(
                        company_id=receiver.id,
                        region_code="310104",
                        region_level="DISTRICT",
                        active=True,
                        review_status="APPROVED",
                    ),
                ]
            )
            db.flush()
            db.add(
                PointsLedger(
                    account_id=receiver_account.id,
                    company_id=receiver.id,
                    ledger_type="RECHARGE",
                    delta=200,
                    balance_after=200,
                    business_type="RECHARGE",
                    business_id=f"pg-claim-recharge-{suffix}",
                    idempotency_key=f"pg-claim-recharge-{suffix}",
                )
            )
            lead = Lead(
                customer_name="并发认领测试客资",
                phone_encrypted=encrypt_text("13800138000"),
                phone_hash=f"pg-claim-{suffix}",
                phone_fingerprint=f"pg-claim-fingerprint-{suffix}",
                region_code="310104",
                status="DISPATCHED",
                source_kind="SUPPLIER_H5",
                supplier_company_id=test_supplier.id,
                duplicate_status="CLEAR",
                review_status="APPROVED",
            )
            db.add(lead)
            db.flush()
            assignment = Assignment(
                lead_id=lead.id,
                company_id=receiver.id,
                supplier_company_id=test_supplier.id,
                receiver_company_id=receiver.id,
                status="PENDING_CLAIM",
                points_price=100,
                claim_points=100,
                lead_snapshot={},
                assigned_by=operator.id,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
            db.add(assignment)
            db.flush()
            lead.current_assignment_id = assignment.id
            db.commit()
            test_company_id = test_supplier.id
            receiver_account_id = receiver_account.id
            assignment_id = assignment.id
            claimant_id = claimant.id

        def _claim_then_wait() -> None:
            with factory() as db:
                claim_assignment(
                    db,
                    assignment_id=assignment_id,
                    company_id=receiver.id,
                    claimed_by=claimant_id,
                )
                writer_ready.set()
                assert allow_commit.wait(10), "purge concurrency test did not release claim"
                db.commit()

        def _purge() -> dict[str, object]:
            with factory() as db:
                snapshot = delete_test_company(
                    db,
                    test_company_id,
                    confirm_name=f"并发认领测试主体 {suffix}",
                )
                db.commit()
                return snapshot

        with ThreadPoolExecutor(max_workers=2) as executor:
            claim_future = executor.submit(_claim_then_wait)
            assert writer_ready.wait(10), "claim transaction did not reach the uncommitted write"
            purge_future = executor.submit(_purge)
            with pytest.raises(AppError) as caught:
                purge_future.result(timeout=5)
            assert caught.value.code == "COMPANY_PURGE_BUSY_RETRY"
            assert caught.value.status_code == 409
            assert not allow_commit.is_set(), "purge must fail before the writer is released"
            allow_commit.set()
            claim_future.result(timeout=15)

        with factory() as db:
            snapshot = delete_test_company(
                db,
                test_company_id,
                confirm_name=f"并发认领测试主体 {suffix}",
            )
            db.commit()

        assert snapshot["purged"]["assignments"] == 1
        assert snapshot["purged"]["points_ledgers"] >= 1
        with factory() as db:
            assert db.get(Company, test_company_id) is None
            assert db.get(Assignment, assignment_id) is None
            assert db.scalar(
                select(PointsLedger).where(PointsLedger.business_id == assignment_id)
            ) is None
            account = db.get(PointsAccount, receiver_account_id)
            assert account is not None and account.balance == 200
    finally:
        allow_commit.set()
        engine.dispose()


def test_postgres_purge_retries_after_reward_settlement_and_removes_new_ledger() -> None:
    engine, factory = _postgres_factory()
    suffix = uuid4().hex[:10]
    writer_ready = Event()
    allow_commit = Event()
    try:
        with factory() as db:
            operator = User(
                username=f"purge_reward_operator_{suffix}",
                display_name="并发奖励测试员",
                status="ACTIVE",
            )
            test_receiver = Company(
                code=f"PG-REWARD-TEST-{suffix}",
                name=f"并发奖励测试主体 {suffix}",
                status="DISABLED",
                is_test=True,
            )
            supplier = Company(
                code=f"PG-REWARD-SUP-{suffix}",
                name=f"并发奖励真实供资方 {suffix}",
                status="ACTIVE",
                is_test=False,
            )
            db.add_all([operator, test_receiver, supplier])
            db.flush()
            test_account = PointsAccount(company_id=test_receiver.id, balance=0, version=1)
            supplier_account = PointsAccount(company_id=supplier.id, balance=0, version=1)
            lead = Lead(
                customer_name="并发奖励外部客资",
                phone_encrypted=encrypt_text("13900139000"),
                phone_hash=f"pg-reward-{suffix}",
                status="CLAIMED",
                source_kind="SUPPLIER_H5",
                supplier_company_id=supplier.id,
            )
            db.add_all([test_account, supplier_account, lead])
            db.flush()
            assignment = Assignment(
                lead_id=lead.id,
                company_id=test_receiver.id,
                supplier_company_id=supplier.id,
                receiver_company_id=test_receiver.id,
                status="CLAIMED",
                points_price=100,
                claim_points=100,
                lead_snapshot={},
                assigned_by=operator.id,
            )
            db.add(assignment)
            db.flush()
            reward = SupplierLeadReward(
                lead_id=lead.id,
                assignment_id=assignment.id,
                supplier_company_id=supplier.id,
                receiver_company_id=test_receiver.id,
                status="OBSERVING",
                claim_points=100,
                reward_ratio_bps=3000,
                reward_points=30,
                rule_version=1,
                rule_snapshot_json={"version": 1, "ratio_bps": 3000},
            )
            db.add(reward)
            db.commit()
            test_company_id = test_receiver.id
            supplier_account_id = supplier_account.id
            assignment_id = assignment.id
            reward_id = reward.id

        def _settle_then_wait() -> None:
            with factory() as db:
                settle_supplier_reward(
                    db,
                    reward_id=reward_id,
                    require_due=False,
                )
                writer_ready.set()
                assert allow_commit.wait(10), "purge concurrency test did not release reward"
                db.commit()

        def _purge() -> dict[str, object]:
            with factory() as db:
                snapshot = delete_test_company(
                    db,
                    test_company_id,
                    confirm_name=f"并发奖励测试主体 {suffix}",
                )
                db.commit()
                return snapshot

        with ThreadPoolExecutor(max_workers=2) as executor:
            reward_future = executor.submit(_settle_then_wait)
            assert writer_ready.wait(10), "reward transaction did not reach the uncommitted write"
            purge_future = executor.submit(_purge)
            with pytest.raises(AppError) as caught:
                purge_future.result(timeout=5)
            assert caught.value.code == "COMPANY_PURGE_BUSY_RETRY"
            assert caught.value.status_code == 409
            assert not allow_commit.is_set(), "purge must fail before the writer is released"
            allow_commit.set()
            reward_future.result(timeout=15)

        with factory() as db:
            snapshot = delete_test_company(
                db,
                test_company_id,
                confirm_name=f"并发奖励测试主体 {suffix}",
            )
            db.commit()

        assert snapshot["purged"]["supplier_rewards"] == 1
        assert snapshot["purged"]["points_ledgers"] >= 1
        with factory() as db:
            assert db.get(Company, test_company_id) is None
            assert db.get(Assignment, assignment_id) is None
            assert db.get(SupplierLeadReward, reward_id) is None
            assert db.scalar(
                select(PointsLedger).where(PointsLedger.business_id == reward_id)
            ) is None
            account = db.get(PointsAccount, supplier_account_id)
            assert account is not None and account.balance == 0
    finally:
        allow_commit.set()
        engine.dispose()


@pytest.mark.parametrize(
    "locked_resource",
    ["return_request", "verification_task"],
)
def test_postgres_purge_returns_retryable_conflict_for_return_workflow_locks(
    locked_resource: str,
) -> None:
    engine, factory = _postgres_factory()
    suffix = uuid4().hex[:10]
    writer_ready = Event()
    allow_commit = Event()
    try:
        with factory() as db:
            operator = User(
                username=f"purge_return_operator_{suffix}",
                display_name="并发退回测试员",
                status="ACTIVE",
            )
            company = Company(
                code=f"PG-RETURN-TEST-{suffix}",
                name=f"并发退回测试主体 {suffix}",
                status="DISABLED",
                is_test=True,
            )
            db.add_all([operator, company])
            db.flush()
            lead = Lead(
                customer_name="并发退回测试客资",
                phone_encrypted=encrypt_text("13700137000"),
                phone_hash=f"pg-return-{suffix}",
                status="CLAIMED",
                source_kind="SUPPLIER_H5",
                supplier_company_id=company.id,
            )
            db.add(lead)
            db.flush()
            assignment = Assignment(
                lead_id=lead.id,
                company_id=company.id,
                supplier_company_id=company.id,
                receiver_company_id=company.id,
                status="RETURN_PENDING",
                points_price=100,
                claim_points=100,
                lead_snapshot={},
                assigned_by=operator.id,
            )
            db.add(assignment)
            db.flush()
            request = ReturnRequest(
                assignment_id=assignment.id,
                lead_id=lead.id,
                company_id=company.id,
                reason_code="TEST_RETURN",
                reason_version=1,
                description="并发退回锁测试",
                status="VERIFYING",
                submitted_by=operator.id,
            )
            db.add(request)
            db.flush()
            task = VerificationTask(
                lead_id=lead.id,
                assignment_id=assignment.id,
                return_request_id=request.id,
                task_type="RETURN_VERIFY",
                status="IN_PROGRESS",
            )
            db.add(task)
            db.commit()
            company_id = company.id
            company_name = company.name
            request_id = request.id
            task_id = task.id

        def _lock_then_wait() -> None:
            model = ReturnRequest if locked_resource == "return_request" else VerificationTask
            resource_id = request_id if locked_resource == "return_request" else task_id
            with factory() as db:
                locked = db.scalar(
                    select(model)
                    .where(model.id == resource_id)
                    .with_for_update()
                )
                assert locked is not None
                writer_ready.set()
                assert allow_commit.wait(10), "purge concurrency test did not release writer"
                db.commit()

        def _purge() -> dict[str, object]:
            with factory() as db:
                snapshot = delete_test_company(
                    db,
                    company_id,
                    confirm_name=company_name,
                )
                db.commit()
                return snapshot

        with ThreadPoolExecutor(max_workers=2) as executor:
            writer_future = executor.submit(_lock_then_wait)
            assert writer_ready.wait(10), f"{locked_resource} writer did not acquire its lock"
            purge_future = executor.submit(_purge)
            with pytest.raises(AppError) as caught:
                purge_future.result(timeout=5)
            assert caught.value.code == "COMPANY_PURGE_BUSY_RETRY"
            assert caught.value.status_code == 409
            assert not allow_commit.is_set(), "purge must fail before the writer is released"
            allow_commit.set()
            writer_future.result(timeout=15)

        with factory() as db:
            snapshot = delete_test_company(
                db,
                company_id,
                confirm_name=company_name,
            )
            db.commit()

        assert snapshot["purged"]["returns"] == 1
        assert snapshot["purged"]["verification_tasks"] == 1
        with factory() as db:
            assert db.get(Company, company_id) is None
            assert db.get(ReturnRequest, request_id) is None
            assert db.get(VerificationTask, task_id) is None
    finally:
        allow_commit.set()
        engine.dispose()

from __future__ import annotations

from apps.api.src.core.models import Assignment, Company, Lead, PointsAccount, PointsLedger, ReturnRequest
from apps.api.src.core.security import encrypt_text, hash_phone
from apps.api.src.services.migration_v12 import backfill_phone_fingerprints_batch
from apps.api.src.services.reconciliation_v12 import reconcile_v12


def test_reconciliation_accepts_legacy_approved_return_refund_linkage(db) -> None:
    company = Company(code="LEG-RET", name="历史退回公司", status="ACTIVE")
    lead = Lead(
        id="legacy-return-lead",
        customer_name="历史客户",
        phone_encrypted=encrypt_text("13800138001"),
        phone_hash=hash_phone("13800138001"),
        status="RETURNED",
        raw_payload={},
    )
    db.add_all([company, lead])
    db.flush()
    backfill_phone_fingerprints_batch(db, secret="F" * 40)

    account = PointsAccount(company_id=company.id, balance=0)
    db.add(account)
    db.flush()
    assignment = Assignment(
        id="legacy-return-assignment",
        lead_id=lead.id,
        company_id=company.id,
        status="RETURNED",
        points_price=100,
        price_version=1,
        lead_snapshot={},
        assigned_by="legacy-reviewer",
    )
    db.add(assignment)
    db.flush()
    claim = PointsLedger(
        account_id=account.id,
        company_id=company.id,
        ledger_type="CLAIM",
        delta=-100,
        balance_after=-100,
        business_type="ASSIGNMENT",
        business_id=assignment.id,
        idempotency_key="legacy-claim",
        metadata_json={},
    )
    refund = PointsLedger(
        account_id=account.id,
        company_id=company.id,
        ledger_type="RETURN",
        delta=100,
        balance_after=0,
        business_type="RETURN_REQUEST",
        business_id="legacy-return-request",
        idempotency_key="legacy-refund",
        related_ledger_id=None,
        metadata_json={},
    )
    db.add_all([claim, refund])
    db.flush()
    refund.related_ledger_id = claim.id
    request = ReturnRequest(
        id="legacy-return-request",
        assignment_id=assignment.id,
        lead_id=lead.id,
        company_id=company.id,
        reason_code="LEGACY",
        description="历史已批准退回",
        status="APPROVED",
        submitted_by="legacy-user",
        refund_points=100,
        refund_ledger_id=refund.id,
    )
    db.add(request)
    db.flush()

    report = reconcile_v12(db)
    codes = {item["code"] for item in report.errors}
    assert "RETURN_REFUND_LEDGER_SEMANTIC_MISMATCH" not in codes
    assert report.metrics["return_refund_ledger_semantic_mismatches"] == 0

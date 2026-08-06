from __future__ import annotations

import pytest

from apps.api.src.core.models import Lead, PointsAccount, PointsLedger
from apps.api.src.core.models_v12 import V12MigrationCheckpoint
from apps.api.src.core.security import encrypt_text, hash_phone
from apps.api.src.core.state_machine_v12 import (
    UnknownLegacyStatus,
    map_legacy_lead_status,
    try_map_legacy_lead_status,
)
from apps.api.src.core.v12_enums import LeadV12Status
from apps.api.src.services.migration_v12 import (
    PHONE_FINGERPRINT_CHECKPOINT,
    backfill_phone_fingerprints_batch,
    preview_phone_fingerprint_backfill,
)
from apps.api.src.services.reconciliation_v12 import reconcile_v12


def _lead(lead_id: str, phone: str, *, encrypted: str | None = None) -> Lead:
    return Lead(
        id=lead_id,
        customer_name=f"客户-{lead_id}",
        phone_encrypted=encrypted or encrypt_text(phone),
        phone_hash=hash_phone(phone),
        status="QUALIFIED",
        raw_payload={},
    )


def test_phone_fingerprint_backfill_is_bounded_resumable_and_idempotent(db) -> None:
    db.add_all([_lead("a-lead", "13800138000"), _lead("b-lead", "13900139000")])
    db.flush()

    first = backfill_phone_fingerprints_batch(db, batch_size=1, secret="F" * 40)
    db.commit()
    assert first.scanned == 1
    assert first.updated == 1
    assert first.complete is False

    second = backfill_phone_fingerprints_batch(db, batch_size=1, secret="F" * 40)
    db.commit()
    assert second.updated == 1
    assert second.complete is True
    assert second.checkpoint_status == "COMPLETED"
    assert all(item.phone_fingerprint for item in db.query(Lead).all())

    third = backfill_phone_fingerprints_batch(db, batch_size=100, secret="F" * 40)
    assert third.scanned == 0
    assert third.complete is True
    checkpoint = db.get(V12MigrationCheckpoint, PHONE_FINGERPRINT_CHECKPOINT)
    assert checkpoint is not None
    assert checkpoint.processed_count == 2
    assert checkpoint.error_count == 0


def test_preview_is_read_only_and_row_errors_never_include_plaintext(db) -> None:
    db.add(_lead("bad-lead", "13800138000", encrypted="not-a-fernet-token"))
    db.flush()

    preview = preview_phone_fingerprint_backfill(db, secret="F" * 40)
    assert preview.scanned == 1
    assert preview.errors == 1
    assert preview.error_samples == ({"lead_id": "bad-lead", "reason": "PHONE_DECRYPT_FAILED"},)
    assert db.get(Lead, "bad-lead").phone_fingerprint is None
    assert db.get(V12MigrationCheckpoint, PHONE_FINGERPRINT_CHECKPOINT) is None

    result = backfill_phone_fingerprints_batch(db, secret="F" * 40)
    db.commit()
    assert result.complete is True
    assert result.checkpoint_status == "COMPLETED_WITH_ERRORS"
    checkpoint = db.get(V12MigrationCheckpoint, PHONE_FINGERPRINT_CHECKPOINT)
    assert checkpoint is not None
    assert "13800138000" not in str(checkpoint.metadata_json)


def test_reconciliation_detects_incomplete_backfill_and_points_mismatch(db) -> None:
    lead = _lead("reconcile-lead", "13700137000")
    db.add(lead)
    db.flush()
    account = PointsAccount(company_id="missing-company", balance=50)
    # SQLite fixtures do not enforce foreign keys by default; this deliberately
    # simulates a historical accounting inconsistency for the read-only checker.
    db.add(account)
    db.flush()
    db.add(
        PointsLedger(
            account_id=account.id,
            company_id="missing-company",
            ledger_type="RECHARGE",
            delta=40,
            balance_after=40,
            business_type="TEST",
            business_id="test",
            idempotency_key="test-ledger",
            metadata_json={},
        )
    )
    db.flush()

    report = reconcile_v12(db)
    codes = {item["code"] for item in report.errors}
    assert "PHONE_FINGERPRINT_INCOMPLETE" in codes
    assert "POINTS_RECONCILIATION_MISMATCH" in codes
    assert report.valid is False


def test_reconciliation_passes_after_clean_backfill(db) -> None:
    db.add(_lead("clean-lead", "13600136000"))
    db.flush()
    result = backfill_phone_fingerprints_batch(db, secret="F" * 40)
    db.commit()
    assert result.complete is True

    report = reconcile_v12(db)
    assert report.valid is True
    assert report.metrics["leads_missing_phone_fingerprint"] == 0


def test_strict_legacy_mapping_refuses_unknown_terminal_fallback() -> None:
    assert try_map_legacy_lead_status(" qualified ") is LeadV12Status.READY_DISPATCH
    assert map_legacy_lead_status("unknown") is LeadV12Status.CLOSED
    with pytest.raises(UnknownLegacyStatus):
        map_legacy_lead_status("unknown", strict=True)

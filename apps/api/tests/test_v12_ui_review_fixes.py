from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from apps.api.src.core.models import Company, Lead, User
from apps.api.src.core.models_v12 import LeadDedupEvent
from apps.api.src.core.security import encrypt_text, fingerprint_phone, hash_phone
from apps.api.src.core.v12_enums import DuplicateDecision, LeadSourceKind, LeadV12Status
from apps.api.src.services.dedup_v12 import override_duplicate


def test_supplier_dedup_override_returns_to_pending_review(db) -> None:
    company = Company(code="SUP-REVIEW", name="供应商复核测试", status="ACTIVE")
    reviewer = User(display_name="复核员", status="ACTIVE")
    db.add_all([company, reviewer])
    db.flush()

    phone = "13900139999"
    now = datetime.now(timezone.utc)
    lead = Lead(
        source_type=LeadSourceKind.SUPPLIER_H5.value,
        source_kind=LeadSourceKind.SUPPLIER_H5.value,
        submitter_user_id=reviewer.id,
        supplier_company_id=company.id,
        customer_name="重复待复核客户",
        phone_encrypted=encrypt_text(phone),
        phone_hash=hash_phone(phone),
        phone_fingerprint=fingerprint_phone(phone),
        consent_confirmed=True,
        city="上海市",
        region_code="310000",
        need_summary="独立建房需求",
        status=LeadV12Status.DUPLICATE.value,
        review_status="DRAFT",
        duplicate_status=DuplicateDecision.HARD_DUPLICATE.value,
        pending_reason=DuplicateDecision.HARD_DUPLICATE.value,
        imported_at=now,
        submitted_at=now,
        raw_payload={},
    )
    db.add(lead)
    db.flush()
    event = LeadDedupEvent(
        lead_id=lead.id,
        phone_fingerprint=lead.phone_fingerprint,
        checkpoint="SUBMIT",
        decision=DuplicateDecision.HARD_DUPLICATE.value,
        window_days=90,
        details_json={"age_days": 10},
    )
    db.add(event)
    db.flush()

    override_duplicate(
        db,
        lead=lead,
        event_id=event.id,
        reason="业务核验确认属于独立家庭的独立需求",
        approved_by=reviewer.id,
    )

    assert lead.status == LeadV12Status.PENDING_REVIEW.value
    assert lead.review_status == "PENDING"
    assert lead.duplicate_status == DuplicateDecision.OVERRIDDEN.value
    assert lead.pending_reason is None


def test_unified_operations_workspace_keeps_source_specific_lead_actions() -> None:
    js = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")

    assert "PLATFORM_MANUAL" in js
    assert "SUPPLIER_H5" in js
    assert "data-platform-pre-dispatch" in js
    assert "data-review-info" in js
    assert "平台补充资料后再处理" in js


def test_supplier_h5_has_real_pagination_controls() -> None:
    js = Path("apps/h5/public/supplier.js").read_text(encoding="utf-8")
    compact = re.sub(r"\s+", "", js)
    assert "listPageSize:20" in compact
    assert "page:state.listPage" in compact
    assert "previous-page" in js
    assert "next-page" in js
    assert "第 ${state.listPage} / ${totalPages} 页" in js
    assert "page:1,page_size:100" not in compact

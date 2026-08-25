from __future__ import annotations

import pytest

from apps.api.src.core.auth import Principal
from apps.api.src.core import models_v12 as _models_v12  # noqa: F401
from apps.api.src.core.errors import AppError
from apps.api.src.core.models import Lead
from apps.api.src.core.security import encrypt_text, hash_phone
from apps.api.src.core.v12_enums import LeadV12Status, VerificationTaskType
from apps.api.src.services.auth_service import create_internal_user
from apps.api.src.services.verification_service import publish_template


def _principal(user, *permissions: str) -> Principal:
    return Principal(
        user_id=user.id,
        display_name=user.display_name,
        company_id=user.company_id,
        role_codes=frozenset(role.code for role in user.roles),
        permission_codes=frozenset(permissions),
        session_version=user.session_version,
    )


def test_pre_dispatch_verification_returns_control_to_operations(db) -> None:
    from apps.api.src.services.pre_dispatch_v12 import (
        assign_pre_dispatch_task,
        decide_pre_dispatch_disposition,
        start_pre_dispatch_task,
        submit_pre_dispatch_verification,
    )

    operation = create_internal_user(
        db,
        username="pre-operation",
        password="simple88",
        display_name="运营",
        role_code="OPERATION",
    )
    telesales = create_internal_user(
        db,
        username="pre-telesales",
        password="simple88",
        display_name="电销",
        role_code="TELESALES",
    )
    unrelated_telesales = create_internal_user(
        db,
        username="pre-other-telesales",
        password="simple88",
        display_name="其他电销",
        role_code="TELESALES",
    )
    lead = Lead(
        source_type="SUPPLIER_H5",
        source_kind="SUPPLIER_H5",
        customer_name="待核验客户",
        phone_encrypted=encrypt_text("13900139009"),
        phone_hash=hash_phone("13900139009"),
        city="上海市",
        region_code="310000",
        category_code="OLD_RENOVATION",
        need_summary="信息完整性待电话确认",
        consent_confirmed=True,
        status=LeadV12Status.PENDING_REVIEW.value,
        review_status="PENDING",
        duplicate_status="CLEAR",
        raw_payload={},
    )
    db.add(lead)
    publish_template(db, code="PRE_DISPATCH", name="前置核验", schema={"fields": []})
    db.flush()

    task = assign_pre_dispatch_task(
        db,
        lead_id=lead.id,
        assignee_user_id=telesales.id,
        assigned_by=operation.id,
        reason="客户需求描述需要电话确认",
        template_code="PRE_DISPATCH",
    )
    assert task.task_type == VerificationTaskType.PRE_DISPATCH_VERIFY.value
    assert lead.status == LeadV12Status.PENDING_TELESALES_VERIFY.value

    with pytest.raises(AppError) as self_start:
        start_pre_dispatch_task(
            db,
            task_id=task.id,
            principal=_principal(unrelated_telesales, "verification.task.start"),
        )
    assert self_start.value.code == "FORBIDDEN"

    start_pre_dispatch_task(
        db,
        task_id=task.id,
        principal=_principal(telesales, "verification.task.start", "lead.phone.read"),
    )
    submit_pre_dispatch_verification(
        db,
        task_id=task.id,
        principal=_principal(telesales, "verification.submit", "lead.phone.read"),
        contact_result="CONNECTED",
        conclusion="INFO_INCOMPLETE",
        note="客户确认预算尚未确定，需要运营决定是否入池",
    )
    assert lead.status == LeadV12Status.PENDING_OPERATION_DISPOSITION.value
    assert lead.pending_reason == "PRE_DISPATCH_INFO_INCOMPLETE"

    decide_pre_dispatch_disposition(
        db,
        lead_id=lead.id,
        principal=_principal(operation, "lead.supplier.review"),
        decision="APPROVE_POOL",
        note="运营确认客户需求真实，转入待派发池",
    )
    assert lead.status == LeadV12Status.READY_DISPATCH.value
    assert lead.review_status == "APPROVED"

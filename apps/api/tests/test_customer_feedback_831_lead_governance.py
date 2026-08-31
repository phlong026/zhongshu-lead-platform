from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from apps.api.src.core.auth import Principal
from apps.api.src.core.enums import AssignmentStatus, PointsLedgerType
from apps.api.src.core.errors import AppError
from apps.api.src.core.models import (
    Assignment,
    AssignmentEvent,
    AuditLog,
    Company,
    Lead,
    LeadDuplicateRelation,
    LeadImportIssue,
    PointsAccount,
    PointsLedger,
    Region,
    ReturnRequest,
    User,
    VerificationSubmission,
    VerificationTask,
)
from apps.api.src.core.models_v12 import SupplierLeadReward
from apps.api.src.core.security import encrypt_text, fingerprint_phone, hash_phone
from apps.api.src.core.v12_enums import (
    LeadSourceKind,
    LeadV12Status,
    ReturnV12Status,
    RewardStatus,
)
from apps.api.src.schemas.v12_lead_supply import PlatformLeadDraftBody
from apps.api.src.services.company_profile_v12 import request_capability, review_capability
from apps.api.src.services.lead_supply_v12 import (
    create_draft,
    delete_test_lead_permanently,
    preview_test_lead_delete,
    release_misdispatched_lead_for_redispatch,
)
from apps.api.src.services.return_v12 import prepare_return_evidence_upload


def _principal(
    user_id: str,
    *,
    roles: tuple[str, ...] = (),
    permissions: tuple[str, ...] = (),
    company_id: str | None = None,
) -> Principal:
    return Principal(
        user_id=user_id,
        display_name="测试用户",
        company_id=company_id,
        role_codes=frozenset(roles),
        permission_codes=frozenset(permissions),
        session_version=1,
    )


def _identity(db, code: str) -> tuple[Company, User]:
    company = Company(code=code, name=f"测试公司-{code}", status="ACTIVE")
    db.add(company)
    db.flush()
    user = User(display_name=f"测试用户-{code}", status="ACTIVE", company_id=company.id)
    db.add(user)
    db.flush()
    return company, user


def _lead(
    *,
    operation_id: str,
    name: str = "错派客户",
    source_kind: LeadSourceKind = LeadSourceKind.PLATFORM_MANUAL,
) -> Lead:
    phone = "13900139931"
    return Lead(
        source_type=source_kind.value,
        source_kind=source_kind.value,
        submitter_user_id=operation_id,
        customer_name=name,
        phone_encrypted=encrypt_text(phone),
        phone_hash=hash_phone(phone),
        phone_fingerprint=fingerprint_phone(phone),
        consent_confirmed=True,
        city="上海市",
        region_code="310000",
        status=LeadV12Status.DISPATCHED.value,
        review_status="APPROVED",
        duplicate_status="CLEAR",
        raw_payload={},
    )


def test_only_platform_drafts_can_set_explicit_test_flag(db) -> None:
    platform_company, platform_user = _identity(db, "TEST-FLAG-PLATFORM")
    supplier_company, supplier_user = _identity(db, "TEST-FLAG-SUPPLIER")
    platform = _principal(
        platform_user.id,
        permissions=("lead.manual.manage",),
    )
    supplier = _principal(
        supplier_user.id,
        permissions=("supplier.lead.manage",),
        company_id=supplier_company.id,
    )
    request_capability(db, supplier_company.id, "LEAD_SUPPLIER")
    review_capability(
        db,
        company_id=supplier_company.id,
        capability_code="LEAD_SUPPLIER",
        approve=True,
        reviewed_by=platform_user.id,
    )

    body = PlatformLeadDraftBody(customer_name="测试客户", is_test=True)
    platform_lead = create_draft(
        db,
        principal=platform,
        source_kind=LeadSourceKind.PLATFORM_MANUAL,
        values=body.model_dump(exclude_none=True),
    )
    supplier_lead = create_draft(
        db,
        principal=supplier,
        source_kind=LeadSourceKind.SUPPLIER_H5,
        values={"customer_name": "供应商伪造测试标记", "is_test": True},
    )

    assert platform_company.id != supplier_company.id
    assert platform_lead.is_test is True
    assert supplier_lead.is_test is False


def test_permanent_delete_requires_superadmin_exact_name_reason_and_no_dispatch_history(db) -> None:
    _, operation_user = _identity(db, "TEST-DELETE-OP")
    superadmin = _principal(operation_user.id, roles=("SUPER_ADMIN",), permissions=("*",))
    operation = _principal(
        operation_user.id,
        roles=("OPERATION",),
        permissions=("lead.manual.manage",),
    )
    test_lead = _lead(operation_id=operation_user.id, name="待清理测试客户")
    test_lead.status = LeadV12Status.DRAFT.value
    test_lead.is_test = True
    db.add(test_lead)
    db.flush()

    with pytest.raises(AppError) as forbidden:
        delete_test_lead_permanently(
            db,
            lead_id=test_lead.id,
            principal=operation,
            confirmed_lead_id=test_lead.id,
            confirmed_customer_name=test_lead.customer_name,
            reason="清理确认无用的测试数据",
        )
    assert forbidden.value.code == "FORBIDDEN"

    with pytest.raises(AppError) as wrong_name:
        delete_test_lead_permanently(
            db,
            lead_id=test_lead.id,
            principal=superadmin,
            confirmed_lead_id=test_lead.id,
            confirmed_customer_name="其他客户",
            reason="清理确认无用的测试数据",
        )
    assert wrong_name.value.code == "TEST_LEAD_CONFIRMATION_MISMATCH"

    deleted = delete_test_lead_permanently(
        db,
        lead_id=test_lead.id,
        principal=superadmin,
        confirmed_lead_id=test_lead.id,
        confirmed_customer_name=test_lead.customer_name,
        reason="清理确认无用的测试数据",
    )
    assert deleted["id"] == test_lead.id
    assert deleted["customer_name"] == "待清理测试客户"
    assert db.get(Lead, test_lead.id) is None


@pytest.mark.parametrize("is_test", [False, True])
def test_permanent_delete_rejects_formal_or_ever_dispatched_lead(db, is_test: bool) -> None:
    company, user = _identity(db, f"TEST-DELETE-HISTORY-{int(is_test)}")
    superadmin = _principal(user.id, roles=("SUPER_ADMIN",), permissions=("*",))
    lead = _lead(operation_id=user.id, name="不可删客户")
    lead.is_test = is_test
    db.add(lead)
    db.flush()
    if is_test:
        assignment = Assignment(
            lead_id=lead.id,
            company_id=company.id,
            status=AssignmentStatus.RELEASED.value,
            points_price=100,
            assigned_by=user.id,
        )
        db.add(assignment)
        db.flush()
        lead.current_assignment_id = None

    with pytest.raises(AppError) as exc_info:
        delete_test_lead_permanently(
            db,
            lead_id=lead.id,
            principal=superadmin,
            confirmed_lead_id=lead.id,
            confirmed_customer_name=lead.customer_name,
            reason="尝试删除不符合门禁的记录",
        )

    assert exc_info.value.code in {
        "TEST_LEAD_REQUIRED",
        "TEST_LEAD_DISPATCH_HISTORY_EXISTS",
    }
    assert db.get(Lead, lead.id) is not None


def test_test_lead_delete_preview_counts_cascades_and_id_confirmation_blocks_same_name_mistake(
    db,
) -> None:
    _, user = _identity(db, "TEST-DELETE-PREVIEW")
    superadmin = _principal(user.id, roles=("SUPER_ADMIN",), permissions=("*",))
    lead = _lead(operation_id=user.id, name="同名测试客户")
    lead.status = LeadV12Status.DRAFT.value
    lead.is_test = True
    same_name = _lead(operation_id=user.id, name="同名测试客户")
    same_name.status = LeadV12Status.DRAFT.value
    same_name.is_test = True
    db.add_all([lead, same_name])
    db.flush()
    issue = LeadImportIssue(
        lead_id=lead.id,
        issue_type="TEST_PREVIEW",
        message="影响预览测试",
    )
    relation = LeadDuplicateRelation(
        lead_id=lead.id,
        duplicate_lead_id=same_name.id,
        reason="TEST_PREVIEW",
    )
    task = VerificationTask(
        lead_id=lead.id,
        status="PENDING",
        template_version=1,
    )
    db.add_all([issue, relation, task])
    db.flush()
    db.add(
        VerificationSubmission(
            task_id=task.id,
            lead_id=lead.id,
            result="VALID",
            answers_json={},
            corrections_json={},
            submitted_by=user.id,
        )
    )
    db.flush()

    preview = preview_test_lead_delete(
        db,
        lead_id=lead.id,
        principal=superadmin,
    )

    assert preview["deletable"] is True
    assert preview["impact"] == {
        "assignment_history": 0,
        "import_issues": 1,
        "duplicate_relations": 1,
        "verification_tasks": 1,
        "verification_submissions": 1,
        "dedup_events": 0,
        "dedup_overrides": 0,
    }
    with pytest.raises(AppError) as wrong_id:
        delete_test_lead_permanently(
            db,
            lead_id=lead.id,
            principal=superadmin,
            confirmed_lead_id=same_name.id,
            confirmed_customer_name=lead.customer_name,
            reason="同名记录必须依赖编号防止误删",
        )
    assert wrong_id.value.code == "TEST_LEAD_ID_CONFIRMATION_MISMATCH"
    assert db.get(Lead, lead.id) is not None

    deleted = delete_test_lead_permanently(
        db,
        lead_id=lead.id,
        principal=superadmin,
        confirmed_lead_id=lead.id,
        confirmed_customer_name=lead.customer_name,
        reason="确认影响后删除这条测试客资及关联记录",
    )
    assert deleted["impact"] == preview["impact"]
    assert db.get(Lead, lead.id) is None
    assert db.get(Lead, same_name.id) is not None


@pytest.mark.parametrize("source_kind", list(LeadSourceKind))
def test_misdispatch_releases_pending_claim_for_every_source_without_deleting_business_facts(
    db,
    source_kind: LeadSourceKind,
) -> None:
    db.add(Region(code="310000", name="上海市", level="CITY", aliases=[], active=True))
    company, user = _identity(db, "MISDISPATCH-PENDING")
    operation = _principal(
        user.id,
        roles=("OPERATION",),
        permissions=("lead.manual.manage",),
    )
    lead = _lead(operation_id=user.id, source_kind=source_kind)
    db.add(lead)
    db.flush()
    assignment = Assignment(
        lead_id=lead.id,
        company_id=company.id,
        status=AssignmentStatus.PENDING_CLAIM.value,
        points_price=100,
        assigned_by=user.id,
        assigned_at=datetime.now(timezone.utc),
    )
    db.add(assignment)
    db.flush()
    lead.current_assignment_id = assignment.id

    result = release_misdispatched_lead_for_redispatch(
        db,
        lead_id=lead.id,
        principal=operation,
        reason="运营误将该客资派给了错误的加盟商",
        expected_snapshot_version=lead.snapshot_version,
    )

    assert result.lead.current_assignment_id is None
    assert result.lead.status == LeadV12Status.READY_DISPATCH.value
    assert result.assignment.status == AssignmentStatus.RELEASED.value
    assert result.assignment.release_reason == "MISDISPATCH_REDISPATCH"
    assert db.get(Lead, lead.id) is not None
    assert db.get(Assignment, assignment.id) is not None


@pytest.mark.parametrize(
    "assignment_status",
    [AssignmentStatus.CLAIMED.value, AssignmentStatus.FOLLOWING.value],
)
def test_misdispatch_refunds_claimed_points_and_cancels_unsettled_reward(
    db,
    assignment_status: str,
) -> None:
    db.add(Region(code="310000", name="上海市", level="CITY", aliases=[], active=True))
    receiver, user = _identity(db, f"MISDISPATCH-REFUND-{assignment_status}")
    supplier, _ = _identity(db, f"MISDISPATCH-SUPPLIER-{assignment_status}")
    operation = _principal(user.id, permissions=("lead.manual.manage",))
    account = PointsAccount(company_id=receiver.id, balance=900, version=1)
    db.add(account)
    db.flush()
    lead = _lead(operation_id=user.id, source_kind=LeadSourceKind.SUPPLIER_H5)
    lead.supplier_company_id = supplier.id
    db.add(lead)
    db.flush()
    assignment = Assignment(
        lead_id=lead.id,
        company_id=receiver.id,
        receiver_company_id=receiver.id,
        supplier_company_id=supplier.id,
        status=assignment_status,
        points_price=100,
        claim_points=100,
        assigned_by=user.id,
    )
    db.add(assignment)
    db.flush()
    lead.current_assignment_id = assignment.id
    claim_ledger = PointsLedger(
        account_id=account.id,
        company_id=receiver.id,
        ledger_type=PointsLedgerType.CLAIM.value,
        delta=-100,
        balance_after=900,
        business_type="V12_ASSIGNMENT_CLAIM",
        business_id=assignment.id,
        idempotency_key=f"misdispatch-claim-{assignment.id}",
        metadata_json={},
        created_by=user.id,
    )
    reward = SupplierLeadReward(
        lead_id=lead.id,
        assignment_id=assignment.id,
        supplier_company_id=supplier.id,
        receiver_company_id=receiver.id,
        status=RewardStatus.OBSERVING.value,
        claim_points=100,
        reward_ratio_bps=3000,
        reward_points=30,
        rule_version=1,
    )
    db.add_all([claim_ledger, reward])
    db.flush()

    result = release_misdispatched_lead_for_redispatch(
        db,
        lead_id=lead.id,
        principal=operation,
        reason="错派撤回并全额退还已扣积分",
        expected_snapshot_version=lead.snapshot_version,
    )

    assert result.refund_ledger is not None
    assert result.refund_ledger.delta == 100
    assert result.refund_ledger.related_ledger_id == claim_ledger.id
    assert result.refund_ledger.business_type == "V12_MISDISPATCH_REDISPATCH_REFUND"
    assert account.balance == 1000
    assert reward.status == RewardStatus.CANCELLED.value
    assert reward.exception_reason == "MISDISPATCH_REDISPATCH"


def test_misdispatch_rejects_settled_supplier_reward(db) -> None:
    receiver, user = _identity(db, "MISDISPATCH-SETTLED")
    supplier, _ = _identity(db, "MISDISPATCH-SETTLED-SUPPLIER")
    operation = _principal(user.id, permissions=("lead.manual.manage",))
    lead = _lead(operation_id=user.id, source_kind=LeadSourceKind.SUPPLIER_H5)
    lead.supplier_company_id = supplier.id
    db.add(lead)
    db.flush()
    assignment = Assignment(
        lead_id=lead.id,
        company_id=receiver.id,
        receiver_company_id=receiver.id,
        supplier_company_id=supplier.id,
        status=AssignmentStatus.PENDING_CLAIM.value,
        points_price=100,
        assigned_by=user.id,
    )
    db.add(assignment)
    db.flush()
    lead.current_assignment_id = assignment.id
    db.add(
        SupplierLeadReward(
            lead_id=lead.id,
            assignment_id=assignment.id,
            supplier_company_id=supplier.id,
            receiver_company_id=receiver.id,
            status=RewardStatus.SETTLED.value,
            claim_points=100,
            reward_ratio_bps=3000,
            reward_points=30,
            rule_version=1,
        )
    )
    db.flush()

    with pytest.raises(AppError) as exc_info:
        release_misdispatched_lead_for_redispatch(
            db,
            lead_id=lead.id,
            principal=operation,
            reason="已结算奖励不应被自动撤回",
            expected_snapshot_version=lead.snapshot_version,
        )

    assert exc_info.value.code == "MISDISPATCH_REWARD_SETTLED"
    assert assignment.status == AssignmentStatus.PENDING_CLAIM.value
    assert lead.current_assignment_id == assignment.id


def test_misdispatch_expires_existing_return_draft_before_releasing_assignment(db) -> None:
    receiver, user = _identity(db, "MISDISPATCH-RETURN-DRAFT")
    operation = _principal(user.id, permissions=("lead.manual.manage",))
    account = PointsAccount(company_id=receiver.id, balance=900, version=1)
    db.add(account)
    db.flush()
    lead = _lead(operation_id=user.id)
    db.add(lead)
    db.flush()
    assignment = Assignment(
        lead_id=lead.id,
        company_id=receiver.id,
        receiver_company_id=receiver.id,
        status=AssignmentStatus.CLAIMED.value,
        points_price=100,
        claim_points=100,
        assigned_by=user.id,
    )
    db.add(assignment)
    db.flush()
    lead.current_assignment_id = assignment.id
    db.add(
        PointsLedger(
            account_id=account.id,
            company_id=receiver.id,
            ledger_type=PointsLedgerType.CLAIM.value,
            delta=-100,
            balance_after=900,
            business_type="V12_ASSIGNMENT_CLAIM",
            business_id=assignment.id,
            idempotency_key=f"misdispatch-return-draft-{assignment.id}",
            metadata_json={},
            created_by=user.id,
        )
    )
    return_request = ReturnRequest(
        assignment_id=assignment.id,
        lead_id=lead.id,
        company_id=receiver.id,
        reason_code="EMPTY_NUMBER",
        reason_version=1,
        description="误派撤回前保存的退回草稿",
        status=ReturnV12Status.DRAFT.value,
        submitted_by=user.id,
    )
    db.add(return_request)
    db.flush()

    result = release_misdispatched_lead_for_redispatch(
        db,
        lead_id=lead.id,
        principal=operation,
        reason="错派撤回时同步关闭未提交的退回草稿",
        expected_snapshot_version=lead.snapshot_version,
    )

    assert result.expired_return_request_id == return_request.id
    assert return_request.status == ReturnV12Status.EXPIRED.value
    assert return_request.reviewed_by == user.id
    assert "错派撤回" in (return_request.review_note or "")
    event = db.scalar(
        select(AssignmentEvent).where(
            AssignmentEvent.assignment_id == assignment.id,
            AssignmentEvent.event_type == "V12_MISDISPATCH_REDISPATCH_RELEASE",
        )
    )
    assert event is not None
    assert event.payload["expired_return_request_id"] == return_request.id


def test_return_evidence_preflight_rejects_released_assignment(db) -> None:
    receiver, user = _identity(db, "RETURN-EVIDENCE-RELEASED")
    principal = _principal(
        user.id,
        roles=("FRANCHISE_OWNER",),
        permissions=("return.own.manage",),
        company_id=receiver.id,
    )
    lead = _lead(operation_id=user.id)
    db.add(lead)
    db.flush()
    assignment = Assignment(
        lead_id=lead.id,
        company_id=receiver.id,
        status=AssignmentStatus.RELEASED.value,
        points_price=100,
        assigned_by=user.id,
    )
    db.add(assignment)
    db.flush()
    item = ReturnRequest(
        assignment_id=assignment.id,
        lead_id=lead.id,
        company_id=receiver.id,
        reason_code="EMPTY_NUMBER",
        reason_version=1,
        description="派发已释放时不可继续保存证据",
        status=ReturnV12Status.DRAFT.value,
        submitted_by=user.id,
    )
    db.add(item)
    db.flush()

    with pytest.raises(AppError) as exc_info:
        prepare_return_evidence_upload(db, request=item, principal=principal)

    assert exc_info.value.code == "RETURN_EVIDENCE_ASSIGNMENT_STATE_INVALID"


@pytest.mark.parametrize(
    "return_status",
    [ReturnV12Status.REJECTED.value, ReturnV12Status.EXPIRED.value],
)
def test_misdispatch_allows_terminal_return_history(
    db,
    return_status: str,
) -> None:
    receiver, user = _identity(db, f"MISDISPATCH-RETURN-{return_status}")
    operation = _principal(user.id, permissions=("lead.manual.manage",))
    lead = _lead(operation_id=user.id)
    db.add(lead)
    db.flush()
    assignment = Assignment(
        lead_id=lead.id,
        company_id=receiver.id,
        status=AssignmentStatus.PENDING_CLAIM.value,
        points_price=100,
        assigned_by=user.id,
    )
    db.add(assignment)
    db.flush()
    lead.current_assignment_id = assignment.id
    item = ReturnRequest(
        assignment_id=assignment.id,
        lead_id=lead.id,
        company_id=receiver.id,
        reason_code="EMPTY_NUMBER",
        reason_version=1,
        description="已经结束的退回历史不应阻塞错派撤回",
        status=return_status,
        submitted_by=user.id,
    )
    db.add(item)
    db.flush()

    result = release_misdispatched_lead_for_redispatch(
        db,
        lead_id=lead.id,
        principal=operation,
        reason="退回历史已结束，继续撤回错误派发",
        expected_snapshot_version=lead.snapshot_version,
    )

    assert result.assignment.status == AssignmentStatus.RELEASED.value
    assert result.expired_return_request_id is None
    assert item.status == return_status


def test_misdispatch_cannot_bypass_pending_fact_correction(db) -> None:
    company, user = _identity(db, "MISDISPATCH-CORRECTION")
    operation = _principal(user.id, permissions=("lead.manual.manage",))
    lead = _lead(operation_id=user.id)
    lead.pending_reason = "CORRECTION_REVIEW_REQUIRED"
    lead.raw_payload = {"correction_issues": ["RECEIVER_AREA_MISMATCH"]}
    db.add(lead)
    db.flush()
    assignment = Assignment(
        lead_id=lead.id,
        company_id=company.id,
        status=AssignmentStatus.PENDING_CLAIM.value,
        points_price=100,
        assigned_by=user.id,
    )
    db.add(assignment)
    db.flush()
    lead.current_assignment_id = assignment.id

    with pytest.raises(AppError) as exc_info:
        release_misdispatched_lead_for_redispatch(
            db,
            lead_id=lead.id,
            principal=operation,
            reason="不能借错派入口跳过客资事实更正流程",
            expected_snapshot_version=lead.snapshot_version,
        )

    assert exc_info.value.code == "MISDISPATCH_CORRECTION_IN_PROGRESS"
    assert assignment.status == AssignmentStatus.PENDING_CLAIM.value
    assert lead.current_assignment_id == assignment.id
    assert lead.raw_payload["correction_issues"] == ["RECEIVER_AREA_MISMATCH"]


@pytest.mark.parametrize(
    ("assignment_status", "error_code"),
    [
        (AssignmentStatus.RETURN_PENDING.value, "MISDISPATCH_RETURN_IN_PROGRESS"),
        (AssignmentStatus.COMPLETED.value, "MISDISPATCH_ASSIGNMENT_NOT_RELEASABLE"),
    ],
)
def test_misdispatch_rejects_terminal_or_returning_assignments(
    db,
    assignment_status: str,
    error_code: str,
) -> None:
    company, user = _identity(db, f"MISDISPATCH-{assignment_status}")
    operation = _principal(user.id, permissions=("lead.manual.manage",))
    lead = _lead(operation_id=user.id)
    db.add(lead)
    db.flush()
    assignment = Assignment(
        lead_id=lead.id,
        company_id=company.id,
        status=assignment_status,
        points_price=100,
        assigned_by=user.id,
    )
    db.add(assignment)
    db.flush()
    lead.current_assignment_id = assignment.id

    with pytest.raises(AppError) as exc_info:
        release_misdispatched_lead_for_redispatch(
            db,
            lead_id=lead.id,
            principal=operation,
            reason="尝试撤回已进入不可撤回状态的客资",
            expected_snapshot_version=lead.snapshot_version,
        )
    assert exc_info.value.code == error_code


def test_test_lead_delete_http_endpoint_writes_audit(api_client) -> None:
    client, factory = api_client
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin123!"},
    )
    assert login.status_code == 200, login.text
    token = login.cookies.get("access_token")
    assert token
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/api/v1/v1.2/platform/leads",
        headers=headers,
        json={"customer_name": "HTTP 待删测试客户", "is_test": True},
    )
    assert created.status_code == 200, created.text
    lead_id = created.json()["data"]["id"]

    operation_login = client.post(
        "/api/v1/auth/login",
        json={"username": "operation", "password": "Operation123!"},
    )
    assert operation_login.status_code == 200, operation_login.text
    operation_token = operation_login.cookies.get("access_token")
    assert operation_token
    preview = client.get(
        f"/api/v1/v1.2/platform/leads/{lead_id}/test-record/impact",
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["data"]["lead_id"] == lead_id
    assert preview.json()["data"]["deletable"] is True
    assert preview.json()["data"]["impact"]["assignment_history"] == 0

    forbidden = client.request(
        "DELETE",
        f"/api/v1/v1.2/platform/leads/{lead_id}/test-record",
        headers={"Authorization": f"Bearer {operation_token}"},
        json={
            "confirmed_lead_id": lead_id,
            "confirmed_customer_name": "HTTP 待删测试客户",
            "reason": "运营人员不允许永久删除测试数据",
        },
    )
    assert forbidden.status_code == 403, forbidden.text

    deleted = client.request(
        "DELETE",
        f"/api/v1/v1.2/platform/leads/{lead_id}/test-record",
        headers=headers,
        json={
            "confirmed_lead_id": lead_id,
            "confirmed_customer_name": "HTTP 待删测试客户",
            "reason": "清理确认无用的 HTTP 测试数据",
        },
    )
    assert deleted.status_code == 200, deleted.text

    with factory() as db:
        assert db.get(Lead, lead_id) is None
        assert db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == "V12_TEST_LEAD_PERMANENT_DELETE",
                AuditLog.resource_id == lead_id,
            )
        ) == 1


def test_misdispatch_http_endpoint_preserves_assignment_and_writes_audit(api_client) -> None:
    client, factory = api_client
    with factory() as db:
        company = db.scalar(select(Company).where(Company.code == "SH-DEMO"))
        operation = db.scalar(select(User).where(User.username == "operation"))
        assert company is not None and operation is not None
        lead = _lead(
            operation_id=operation.id,
            name="HTTP 错派客户",
            source_kind=LeadSourceKind.FEISHU_IMPORT,
        )
        db.add(lead)
        db.flush()
        assignment = Assignment(
            lead_id=lead.id,
            company_id=company.id,
            receiver_company_id=company.id,
            status=AssignmentStatus.PENDING_CLAIM.value,
            points_price=100,
            assigned_by=operation.id,
        )
        db.add(assignment)
        db.flush()
        lead.current_assignment_id = assignment.id
        db.commit()
        lead_id = lead.id
        assignment_id = assignment.id
        snapshot_version = lead.snapshot_version

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "operation", "password": "Operation123!"},
    )
    assert login.status_code == 200, login.text
    token = login.cookies.get("access_token")
    assert token
    released = client.post(
        f"/api/v1/v1.2/platform/leads/{lead_id}/misdispatch/release-for-redispatch",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "reason": "运营误将飞书客资派给了错误的加盟商",
            "expected_snapshot_version": snapshot_version,
        },
    )
    assert released.status_code == 200, released.text
    assert released.json()["data"]["assignment"]["status"] == AssignmentStatus.RELEASED.value

    with factory() as db:
        assert db.get(Lead, lead_id) is not None
        assert db.get(Assignment, assignment_id) is not None
        assert db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == "V12_PLATFORM_LEAD_MISDISPATCH_REDISPATCH",
                AuditLog.resource_id == lead_id,
            )
        ) == 1
        assert db.scalar(
            select(func.count(AssignmentEvent.id)).where(
                AssignmentEvent.assignment_id == assignment_id,
                AssignmentEvent.event_type == "V12_MISDISPATCH_REDISPATCH_RELEASE",
            )
        ) == 1

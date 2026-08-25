from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import models_v12 as _models_v12  # noqa: F401
from ..core.auth import Principal
from ..core.enums import VerificationTaskStatus
from ..core.errors import AppError
from ..core.models import Lead, Role, User, VerificationSubmission, VerificationTask
from ..core.state_machine_v12 import assert_lead_transition
from ..core.v12_enums import LeadSourceKind, LeadV12Status, VerificationTaskType
from .verification_service import latest_published_template


_ACTIVE_TASK_STATUSES = {
    VerificationTaskStatus.ASSIGNED.value,
    VerificationTaskStatus.IN_PROGRESS.value,
}
_CONCLUSIONS = {"QUALIFIED", "INFO_INCOMPLETE", "UNVERIFIABLE", "INVALID", "DUPLICATE"}
_DISPOSITIONS = {"APPROVE_POOL", "RETURN_REWORK", "DUPLICATE", "CLOSE"}


def _lead_or_raise(db: Session, lead_id: str, *, lock: bool = False) -> Lead:
    stmt = select(Lead).where(Lead.id == lead_id)
    if lock:
        stmt = stmt.with_for_update()
    lead = db.scalar(stmt)
    if lead is None:
        raise AppError("LEAD_NOT_FOUND", "客资不存在", 404)
    return lead


def _telesales_or_raise(db: Session, user_id: str) -> User:
    user = db.scalar(
        select(User)
        .join(User.roles)
        .where(User.id == user_id, User.status == "ACTIVE", Role.code == "TELESALES")
    )
    if user is None:
        raise AppError("PRE_DISPATCH_TELESALES_REQUIRED", "任务只能派发给启用中的电销人员", 422)
    return user


def _task_or_raise(db: Session, task_id: str, *, lock: bool = False) -> VerificationTask:
    stmt = select(VerificationTask).where(
        VerificationTask.id == task_id,
        VerificationTask.task_type == VerificationTaskType.PRE_DISPATCH_VERIFY.value,
    )
    if lock:
        stmt = stmt.with_for_update()
    task = db.scalar(stmt)
    if task is None:
        raise AppError("PRE_DISPATCH_TASK_NOT_FOUND", "前置电销核验任务不存在", 404)
    return task


def assign_pre_dispatch_task(
    db: Session,
    *,
    lead_id: str,
    assignee_user_id: str,
    assigned_by: str,
    reason: str,
    template_code: str = "PRE_DISPATCH",
) -> VerificationTask:
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise AppError("PRE_DISPATCH_REASON_REQUIRED", "派发前置核验必须填写原因", 422)
    lead = _lead_or_raise(db, lead_id, lock=True)
    if lead.status not in {
        LeadV12Status.PENDING_REVIEW.value,
        LeadV12Status.PENDING_TELESALES_VERIFY.value,
    }:
        raise AppError("PRE_DISPATCH_LEAD_STATE_INVALID", "当前客资不可派发前置电销核验", 409)
    _telesales_or_raise(db, assignee_user_id)
    active = db.scalar(
        select(VerificationTask)
        .where(
            VerificationTask.lead_id == lead.id,
            VerificationTask.task_type == VerificationTaskType.PRE_DISPATCH_VERIFY.value,
            VerificationTask.status.in_(_ACTIVE_TASK_STATUSES),
        )
        .with_for_update()
    )
    if active is not None:
        if active.assignee_user_id == assignee_user_id:
            return active
        if active.status == VerificationTaskStatus.IN_PROGRESS.value:
            raise AppError("PRE_DISPATCH_TASK_IN_PROGRESS", "核验已开始，不能直接改派", 409)
        active.assignee_user_id = assignee_user_id
        active.assigned_by = assigned_by
        active.assigned_at = datetime.now(timezone.utc)
        active.lock_version += 1
        return active
    template = latest_published_template(db, template_code)
    task = VerificationTask(
        lead_id=lead.id,
        template_id=template.id,
        template_version=template.version,
        task_type=VerificationTaskType.PRE_DISPATCH_VERIFY.value,
        status=VerificationTaskStatus.ASSIGNED.value,
        assignee_user_id=assignee_user_id,
        assigned_by=assigned_by,
        assigned_at=datetime.now(timezone.utc),
    )
    db.add(task)
    assert_lead_transition(lead.status, LeadV12Status.PENDING_TELESALES_VERIFY)
    lead.status = LeadV12Status.PENDING_TELESALES_VERIFY.value
    lead.pending_reason = normalized_reason
    db.flush()
    return task


def start_pre_dispatch_task(db: Session, *, task_id: str, principal: Principal) -> VerificationTask:
    task = _task_or_raise(db, task_id, lock=True)
    if task.status == VerificationTaskStatus.IN_PROGRESS.value and task.assignee_user_id == principal.user_id:
        return task
    if task.status != VerificationTaskStatus.ASSIGNED.value or task.assignee_user_id is None:
        raise AppError("PRE_DISPATCH_TASK_NOT_ASSIGNED", "任务须由运营派发后才能开始", 409)
    if task.assignee_user_id != principal.user_id:
        raise AppError("FORBIDDEN", "任务已派发给其他电销人员", 403)
    task.status = VerificationTaskStatus.IN_PROGRESS.value
    task.started_at = task.started_at or datetime.now(timezone.utc)
    task.lock_version += 1
    db.flush()
    return task


def submit_pre_dispatch_verification(
    db: Session,
    *,
    task_id: str,
    principal: Principal,
    contact_result: str,
    conclusion: str,
    note: str,
) -> VerificationSubmission:
    task = _task_or_raise(db, task_id, lock=True)
    normalized_conclusion = conclusion.strip().upper()
    normalized_note = note.strip()
    if normalized_conclusion not in _CONCLUSIONS:
        raise AppError("PRE_DISPATCH_CONCLUSION_INVALID", "前置核验结论无效", 422)
    if not normalized_note:
        raise AppError("PRE_DISPATCH_NOTE_REQUIRED", "提交核验结论必须填写事实说明", 422)
    if task.status == VerificationTaskStatus.SUBMITTED.value and task.assignee_user_id == principal.user_id:
        submission = db.scalar(
            select(VerificationSubmission)
            .where(VerificationSubmission.task_id == task.id)
            .order_by(VerificationSubmission.created_at.desc())
        )
        if submission is not None:
            return submission
    if task.status != VerificationTaskStatus.IN_PROGRESS.value or task.assignee_user_id != principal.user_id:
        raise AppError("PRE_DISPATCH_TASK_NOT_OWNED", "任务不属于当前电销人员或尚未开始", 409)
    lead = _lead_or_raise(db, task.lead_id, lock=True)
    if lead.status != LeadV12Status.PENDING_TELESALES_VERIFY.value:
        raise AppError("PRE_DISPATCH_LEAD_STATE_INVALID", "客资当前不在前置电销核验阶段", 409)
    task.contact_result = contact_result.strip().upper()
    task.verification_conclusion = normalized_conclusion
    task.status = VerificationTaskStatus.SUBMITTED.value
    task.submitted_at = datetime.now(timezone.utc)
    task.lock_version += 1
    assert_lead_transition(lead.status, LeadV12Status.PENDING_OPERATION_DISPOSITION)
    lead.status = LeadV12Status.PENDING_OPERATION_DISPOSITION.value
    lead.pending_reason = f"PRE_DISPATCH_{normalized_conclusion}"
    submission = VerificationSubmission(
        task_id=task.id,
        lead_id=lead.id,
        result=normalized_conclusion,
        answers_json={},
        corrections_json={},
        note=normalized_note,
        submitted_by=principal.user_id,
    )
    db.add(submission)
    db.flush()
    return submission


def decide_pre_dispatch_disposition(
    db: Session,
    *,
    lead_id: str,
    principal: Principal,
    decision: str,
    note: str,
) -> Lead:
    normalized_decision = decision.strip().upper()
    normalized_note = note.strip()
    if normalized_decision not in _DISPOSITIONS:
        raise AppError("PRE_DISPATCH_DECISION_INVALID", "运营处置决定无效", 422)
    if not normalized_note:
        raise AppError("PRE_DISPATCH_NOTE_REQUIRED", "运营处置必须填写说明", 422)
    lead = _lead_or_raise(db, lead_id, lock=True)
    if lead.status != LeadV12Status.PENDING_OPERATION_DISPOSITION.value:
        raise AppError("PRE_DISPATCH_LEAD_STATE_INVALID", "当前客资不在待运营处置阶段", 409)
    task = db.scalar(
        select(VerificationTask)
        .where(
            VerificationTask.lead_id == lead.id,
            VerificationTask.task_type == VerificationTaskType.PRE_DISPATCH_VERIFY.value,
            VerificationTask.status == VerificationTaskStatus.SUBMITTED.value,
        )
        .order_by(VerificationTask.submitted_at.desc())
        .with_for_update()
    )
    if task is None or not task.verification_conclusion:
        raise AppError("PRE_DISPATCH_CONCLUSION_REQUIRED", "电销提交事实结论后才能运营处置", 409)
    if normalized_decision == "APPROVE_POOL":
        target = LeadV12Status.READY_DISPATCH
        lead.review_status = "APPROVED"
        lead.pending_reason = None
    elif normalized_decision == "RETURN_REWORK":
        target = LeadV12Status.DRAFT
        lead.review_status = "DRAFT"
        lead.pending_reason = "PRE_DISPATCH_REWORK_REQUIRED"
    elif normalized_decision == "DUPLICATE":
        target = LeadV12Status.DUPLICATE
        lead.review_status = "PENDING"
        lead.pending_reason = "PRE_DISPATCH_DUPLICATE"
    else:
        target = LeadV12Status.CLOSED
        lead.review_status = "REJECTED"
        lead.pending_reason = "PRE_DISPATCH_CLOSED"
    assert_lead_transition(lead.status, target)
    lead.status = target.value
    lead.review_note = normalized_note
    lead.reviewed_at = datetime.now(timezone.utc)
    db.flush()
    return lead

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.enums import LeadStatus
from ..core.models import (
    Assignment,
    Lead,
    ReturnRequest,
    VerificationSubmission,
    VerificationTask,
)
from ..core.models_v12 import SupplierLeadReward

STAGING_CLEANUP_STATUSES = (
    LeadStatus.IMPORTED.value,
    LeadStatus.IMPORT_ERROR.value,
    LeadStatus.DUPLICATE_REVIEW.value,
)


def preview_feishu_staging_cleanup(db: Session) -> dict:
    lead_ids = _candidate_lead_ids(db)
    return _preview_for_lead_ids(db, lead_ids)


def _preview_for_lead_ids(db: Session, lead_ids: list[str]) -> dict:
    blocked_ids = _blocked_lead_ids(db, lead_ids)
    deletable_ids = [lead_id for lead_id in lead_ids if lead_id not in blocked_ids]
    return {
        "candidate_count": len(lead_ids),
        "deletable_count": len(deletable_ids),
        "blocked_count": len(blocked_ids),
        "blocked_reasons": _blocked_reason_counts(db, blocked_ids),
    }


def _candidate_lead_ids(db: Session) -> list[str]:
    statement = select(Lead.id).where(
        Lead.source_type == "FEISHU",
        Lead.status.in_(STAGING_CLEANUP_STATUSES),
    )
    return list(db.scalars(statement).all())


def _blocked_lead_ids(db: Session, lead_ids: list[str]) -> set[str]:
    if not lead_ids:
        return set()
    blocked: set[str] = set()
    for model in (Assignment, ReturnRequest, VerificationTask, VerificationSubmission, SupplierLeadReward):
        blocked.update(db.scalars(select(model.lead_id).where(model.lead_id.in_(lead_ids))).all())
    blocked.update(db.scalars(select(Lead.id).where(Lead.id.in_(lead_ids), Lead.current_assignment_id.is_not(None))).all())
    return blocked


def _blocked_reason_counts(db: Session, blocked_ids: set[str]) -> dict[str, int]:
    if not blocked_ids:
        return {}
    reasons = {
        "assignment": db.scalar(select(func.count(Assignment.id)).where(Assignment.lead_id.in_(blocked_ids))) or 0,
        "return_request": db.scalar(select(func.count(ReturnRequest.id)).where(ReturnRequest.lead_id.in_(blocked_ids))) or 0,
        "verification_task": db.scalar(select(func.count(VerificationTask.id)).where(VerificationTask.lead_id.in_(blocked_ids))) or 0,
        "verification_submission": db.scalar(select(func.count(VerificationSubmission.id)).where(VerificationSubmission.lead_id.in_(blocked_ids))) or 0,
        "supplier_reward": db.scalar(select(func.count(SupplierLeadReward.id)).where(SupplierLeadReward.lead_id.in_(blocked_ids))) or 0,
    }
    current_assignment = db.scalar(
        select(func.count(Lead.id)).where(Lead.id.in_(blocked_ids), Lead.current_assignment_id.is_not(None))
    ) or 0
    if current_assignment:
        reasons["current_assignment"] = current_assignment
    return {key: value for key, value in reasons.items() if value}

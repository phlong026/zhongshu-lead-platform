from __future__ import annotations

from hashlib import sha256

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from ..core.enums import LeadStatus
from ..core.errors import AppError
from ..core.models import (
    Assignment,
    Lead,
    LeadDuplicateRelation,
    LeadImportIssue,
    ReturnRequest,
    VerificationSubmission,
    VerificationTask,
)
from ..core.models_v12 import DedupOverride, LeadDedupEvent, SupplierLeadReward

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
        "cleanup_token": _cleanup_token(deletable_ids),
    }


def _cleanup_token(lead_ids: list[str]) -> str:
    payload = "\n".join(sorted(lead_ids)).encode("utf-8")
    return sha256(payload).hexdigest()


def delete_feishu_staging_leads(
    db: Session,
    *,
    expected_deletable_count: int,
    cleanup_token: str,
) -> dict:
    # Lock the exact candidate snapshot used for this destructive operation.
    # New rows arriving later are not part of the locked id set and cannot be
    # deleted accidentally.
    lead_ids = _candidate_lead_ids(db, for_update=True)
    preview = _preview_for_lead_ids(db, lead_ids)
    if (
        preview["deletable_count"] != expected_deletable_count
        or preview["cleanup_token"] != cleanup_token
    ):
        raise AppError(
            "STAGING_CLEANUP_PREVIEW_STALE",
            "暂存区数据已变化，请重新预览后再清理",
            409,
            {**preview, "expected_deletable_count": expected_deletable_count},
        )

    blocked_ids = _blocked_lead_ids(db, lead_ids)
    deletable_ids = [lead_id for lead_id in lead_ids if lead_id not in blocked_ids]
    if not deletable_ids:
        return {**preview, "deleted_count": 0}

    db.execute(delete(LeadImportIssue).where(LeadImportIssue.lead_id.in_(deletable_ids)))
    db.execute(
        delete(LeadDuplicateRelation).where(
            or_(
                LeadDuplicateRelation.lead_id.in_(deletable_ids),
                LeadDuplicateRelation.duplicate_lead_id.in_(deletable_ids),
            )
        )
    )
    db.execute(delete(DedupOverride).where(DedupOverride.lead_id.in_(deletable_ids)))
    db.execute(delete(LeadDedupEvent).where(LeadDedupEvent.lead_id.in_(deletable_ids)))
    db.execute(
        update(LeadDedupEvent)
        .where(LeadDedupEvent.matched_lead_id.in_(deletable_ids))
        .values(matched_lead_id=None)
    )
    deleted = db.execute(
        delete(Lead).where(
            Lead.id.in_(deletable_ids),
            Lead.source_type == "FEISHU",
            Lead.status.in_(STAGING_CLEANUP_STATUSES),
        )
    )
    if deleted.rowcount != len(deletable_ids):
        raise AppError(
            "STAGING_CLEANUP_CONFLICT",
            "暂存区清理期间数据已变化，本次操作已取消",
            409,
        )
    return {**preview, "deleted_count": deleted.rowcount}


def _candidate_lead_ids(db: Session, *, for_update: bool = False) -> list[str]:
    statement = select(Lead.id).where(
        Lead.source_type == "FEISHU",
        Lead.status.in_(STAGING_CLEANUP_STATUSES),
    )
    if for_update:
        statement = statement.with_for_update()
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

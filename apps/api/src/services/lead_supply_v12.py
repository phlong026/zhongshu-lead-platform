from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.auth import Principal
from ..core.errors import AppError
from ..core.models import Lead, Region
from ..core.models_v12 import LeadDedupEvent
from ..core.security import decrypt_text, encrypt_text, fingerprint_phone, hash_phone, mask_phone, normalize_phone
from ..core.v12_enums import LeadReviewStatus, LeadSourceKind, LeadV12Status
from .company_profile_v12 import require_lead_capability
from .dedup_v12 import DedupResult, apply_submission_decision, evaluate_phone


EDITABLE_FIELDS = {
    "customer_name",
    "phone",
    "province",
    "city",
    "district",
    "region_code",
    "category_code",
    "brand_code",
    "source_channel",
    "need_summary",
    "budget_min",
    "budget_max",
    "acquisition_cost_cents",
    "consent_confirmed",
}


def _clean_text(value: Any, *, empty_to_none: bool = True) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if empty_to_none and not cleaned:
        return None
    return cleaned


def _assert_draft(lead: Lead) -> None:
    if lead.status != LeadV12Status.DRAFT.value:
        raise AppError("LEAD_NOT_EDITABLE", "仅草稿状态客资允许编辑", 409)


def _assert_owner(lead: Lead, principal: Principal, *, supplier: bool) -> None:
    if principal.can("*"):
        return
    if supplier:
        if not principal.company_id or lead.supplier_company_id != principal.company_id:
            raise AppError("FORBIDDEN", "无权访问其他公司的供应商客资", 403)
    elif lead.submitter_user_id != principal.user_id:
        raise AppError("FORBIDDEN", "无权修改其他录入人的客资草稿", 403)


def create_draft(
    db: Session,
    *,
    principal: Principal,
    source_kind: LeadSourceKind,
    values: dict[str, Any],
) -> Lead:
    supplier_company_id: str | None = None
    if source_kind is LeadSourceKind.SUPPLIER_H5:
        require_lead_capability(db, principal.company_id, "LEAD_SUPPLIER")
        supplier_company_id = principal.company_id
    placeholder_phone = ""
    lead = Lead(
        source_type=source_kind.value,
        source_kind=source_kind.value,
        submitter_user_id=principal.user_id,
        supplier_company_id=supplier_company_id,
        customer_name="未填写",
        phone_encrypted=encrypt_text(placeholder_phone),
        phone_hash=hash_phone(placeholder_phone),
        phone_fingerprint=None,
        consent_confirmed=False,
        status=LeadV12Status.DRAFT.value,
        review_status=LeadReviewStatus.DRAFT.value,
        duplicate_status=None,
        raw_payload={},
    )
    db.add(lead)
    db.flush()
    update_draft(db, lead=lead, principal=principal, values=values)
    return lead


def update_draft(
    db: Session,
    *,
    lead: Lead,
    principal: Principal,
    values: dict[str, Any],
) -> Lead:
    _assert_draft(lead)
    supplier = lead.source_kind == LeadSourceKind.SUPPLIER_H5.value
    _assert_owner(lead, principal, supplier=supplier)
    for field, raw_value in values.items():
        if field not in EDITABLE_FIELDS:
            continue
        if field == "phone":
            if raw_value is None:
                continue
            normalized = normalize_phone(str(raw_value))
            if normalized and (len(normalized) != 11 or not normalized.startswith("1")):
                raise AppError("LEAD_PHONE_INVALID", "手机号格式错误", 422)
            lead.phone_encrypted = encrypt_text(normalized)
            lead.phone_hash = hash_phone(normalized)
            lead.phone_fingerprint = fingerprint_phone(normalized) if normalized else None
            continue
        if field in {"budget_min", "budget_max", "acquisition_cost_cents"}:
            setattr(lead, field, raw_value)
            continue
        if field == "consent_confirmed":
            lead.consent_confirmed = bool(raw_value)
            continue
        setattr(lead, field, _clean_text(raw_value))
    if lead.customer_name is None:
        lead.customer_name = "未填写"
    db.flush()
    return lead


def discard_draft(
    db: Session,
    *,
    lead: Lead,
    principal: Principal,
) -> None:
    _assert_owner(lead, principal, supplier=True)
    if lead.source_kind != LeadSourceKind.SUPPLIER_H5.value:
        raise AppError("LEAD_SOURCE_INVALID", "仅供应商客资草稿支持在此删除", 409)
    _assert_draft(lead)
    db.delete(lead)
    db.flush()


def reopen_rejected_supplier_lead(
    db: Session,
    *,
    lead: Lead,
    principal: Principal,
) -> Lead:
    _assert_owner(lead, principal, supplier=True)
    if lead.source_kind != LeadSourceKind.SUPPLIER_H5.value:
        raise AppError("LEAD_SOURCE_INVALID", "仅供应商上传客资支持修改后重新提交", 409)
    if (
        lead.status != LeadV12Status.INVALID.value
        or lead.review_status != LeadReviewStatus.REJECTED.value
    ):
        raise AppError("LEAD_REVISION_NOT_ALLOWED", "仅平台退回的客资支持修改后重新提交", 409)
    lead.status = LeadV12Status.DRAFT.value
    lead.review_status = LeadReviewStatus.DRAFT.value
    lead.submitted_at = None
    lead.reviewed_at = None
    lead.duplicate_status = None
    lead.pending_reason = None
    db.flush()
    return lead


def _validate_submission(db: Session, lead: Lead) -> str:
    phone = normalize_phone(decrypt_text(lead.phone_encrypted) or "")
    errors: dict[str, str] = {}
    if not lead.customer_name or lead.customer_name == "未填写":
        errors["customer_name"] = "客户姓名必填"
    if len(phone) != 11 or not phone.startswith("1"):
        errors["phone"] = "手机号格式错误"
    if not lead.city:
        errors["city"] = "城市必填"
    if not lead.region_code:
        errors["region_code"] = "标准地区编码必填"
    elif not db.scalar(select(Region.code).where(Region.code == lead.region_code, Region.active.is_(True))):
        errors["region_code"] = "标准地区编码无效或已停用"
    if not lead.need_summary:
        errors["need_summary"] = "客户需求必填"
    if not lead.consent_confirmed:
        errors["consent_confirmed"] = "必须确认已获得客户信息授权"
    if lead.budget_min is not None and lead.budget_max is not None and lead.budget_min > lead.budget_max:
        errors["budget_max"] = "预算上限不能低于预算下限"
    if errors:
        raise AppError("LEAD_SUBMISSION_INVALID", "客资提交校验失败", 422, {"fields": errors})
    return phone


def submit_draft(
    db: Session,
    *,
    lead: Lead,
    principal: Principal,
    checkpoint: str = "SUBMIT",
) -> DedupResult:
    _assert_draft(lead)
    supplier = lead.source_kind == LeadSourceKind.SUPPLIER_H5.value
    _assert_owner(lead, principal, supplier=supplier)
    if supplier:
        require_lead_capability(db, principal.company_id, "LEAD_SUPPLIER")
    phone = _validate_submission(db, lead)
    if supplier:
        lead.review_note = None
        lead.reviewed_at = None
    now = datetime.now(timezone.utc)
    lead.submitted_at = now
    lead.imported_at = lead.imported_at or now
    result = evaluate_phone(db, lead=lead, normalized_phone=phone, checkpoint=checkpoint, now=now)
    apply_submission_decision(lead, result)
    db.flush()
    return result


def review_supplier_lead(
    db: Session,
    *,
    lead: Lead,
    reviewer: Principal,
    approve: bool,
    note: str | None,
) -> DedupResult | None:
    if lead.source_kind != LeadSourceKind.SUPPLIER_H5.value:
        raise AppError("LEAD_SOURCE_INVALID", "仅供应商上传客资需要资料初审", 409)
    if lead.status not in {LeadV12Status.PENDING_REVIEW.value, LeadV12Status.DUPLICATE.value}:
        raise AppError("LEAD_REVIEW_STATE_INVALID", "当前客资状态不可初审", 409)
    lead.review_note = _clean_text(note)
    lead.reviewed_at = datetime.now(timezone.utc)
    if not approve:
        if not lead.review_note:
            raise AppError("REVIEW_NOTE_REQUIRED", "驳回时必须填写原因", 422)
        lead.review_status = LeadReviewStatus.REJECTED.value
        lead.status = LeadV12Status.INVALID.value
        lead.pending_reason = "SUPPLIER_REVIEW_REJECTED"
        db.flush()
        return None

    phone = _validate_submission(db, lead)
    result = evaluate_phone(
        db,
        lead=lead,
        normalized_phone=phone,
        checkpoint="SUPPLIER_REVIEW",
        now=datetime.now(timezone.utc),
    )
    if result.blocks_dispatch:
        lead.review_status = LeadReviewStatus.PENDING.value
        lead.status = LeadV12Status.DUPLICATE.value
        lead.pending_reason = result.decision.value
    else:
        lead.review_status = LeadReviewStatus.APPROVED.value
        lead.status = LeadV12Status.READY_DISPATCH.value
        lead.pending_reason = None
    db.flush()
    return result


def get_lead_or_404(db: Session, lead_id: str) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise AppError("LEAD_NOT_FOUND", "客资不存在", 404)
    return lead


def list_supplier_leads(
    db: Session,
    *,
    company_id: str,
    status: str | None,
    page_no: int,
    page_size: int,
) -> tuple[list[Lead], int]:
    stmt = select(Lead).where(
        Lead.source_kind == LeadSourceKind.SUPPLIER_H5.value,
        Lead.supplier_company_id == company_id,
    )
    count_stmt = select(func.count(Lead.id)).where(
        Lead.source_kind == LeadSourceKind.SUPPLIER_H5.value,
        Lead.supplier_company_id == company_id,
    )
    if status:
        stmt = stmt.where(Lead.status == status)
        count_stmt = count_stmt.where(Lead.status == status)
    total = db.scalar(count_stmt) or 0
    items = list(
        db.scalars(
            stmt.order_by(Lead.created_at.desc()).offset((page_no - 1) * page_size).limit(page_size)
        ).all()
    )
    return items, total


def latest_dedup_event(db: Session, lead_id: str) -> LeadDedupEvent | None:
    return db.scalar(
        select(LeadDedupEvent)
        .where(LeadDedupEvent.lead_id == lead_id)
        .order_by(LeadDedupEvent.created_at.desc())
    )


def lead_supply_to_dict(lead: Lead, principal: Principal | None = None) -> dict[str, Any]:
    phone = decrypt_text(lead.phone_encrypted)
    can_view_phone = bool(
        principal
        and (
            principal.can("*")
            or principal.can("lead.phone.read")
            or (principal.company_id and lead.supplier_company_id == principal.company_id)
            or lead.submitter_user_id == principal.user_id
        )
    )
    return {
        "id": lead.id,
        "source_kind": lead.source_kind,
        "submitter_user_id": lead.submitter_user_id,
        "supplier_company_id": lead.supplier_company_id,
        "customer_name": lead.customer_name,
        "phone": phone if can_view_phone else None,
        "phone_masked": mask_phone(phone),
        "province": lead.province,
        "city": lead.city,
        "district": lead.district,
        "region_code": lead.region_code,
        "category_code": lead.category_code,
        "brand_code": lead.brand_code,
        "source_channel": lead.source_channel,
        "need_summary": lead.need_summary,
        "budget_min": lead.budget_min,
        "budget_max": lead.budget_max,
        "acquisition_cost_cents": lead.acquisition_cost_cents,
        "consent_confirmed": lead.consent_confirmed,
        "status": lead.status,
        "review_status": lead.review_status,
        "review_note": lead.review_note,
        "duplicate_status": lead.duplicate_status,
        "pending_reason": lead.pending_reason,
        "submitted_at": lead.submitted_at.isoformat() if lead.submitted_at else None,
        "reviewed_at": lead.reviewed_at.isoformat() if lead.reviewed_at else None,
        "created_at": lead.created_at.isoformat(),
        "updated_at": lead.updated_at.isoformat(),
    }

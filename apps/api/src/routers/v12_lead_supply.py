from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.auth import CurrentPrincipal, require_permissions
from ..core.database import get_db
from ..core.errors import AppError
from ..core.models import Company, Lead
from ..core.models_v12 import CompanyLeadCapability, CompanyServiceAreaV12
from ..core.responses import ok, page
from ..core.v12_enums import LeadSourceKind
from ..schemas.v12_lead_supply import (
    CapabilityRequestBody,
    CapabilityReviewBody,
    CompanyProfileBulkApproveBody,
    DedupOverrideBody,
    LeadDraftBody,
    LeadDraftUpdateBody,
    ServiceAreaReplaceBody,
    ServiceAreaReviewBody,
    SupplierReviewBody,
)
from ..services.audit import write_audit
from ..services.company_profile_v12 import (
    list_capabilities,
    list_service_areas,
    approve_pending_profile,
    replace_service_areas,
    request_capability,
    require_active_company,
    review_capability,
    review_service_area,
)
from ..services.dedup_v12 import override_duplicate
from ..services.china_regions import region_by_code
from ..services.lead_supply_v12 import (
    create_draft,
    discard_draft,
    get_lead_or_404,
    lead_supply_to_dict,
    list_supplier_leads,
    reopen_rejected_supplier_lead,
    review_supplier_lead,
    submit_draft,
    update_draft,
)
from ..services.pre_dispatch_v12 import assign_pre_dispatch_task

router = APIRouter(prefix="/v1.2", tags=["v1.2-lead-supply"])


def _dedup_dict(result) -> dict | None:
    if result is None:
        return None
    return {
        "decision": result.decision.value,
        "matched_lead_id": result.matched_lead_id,
        "window_days": result.window_days,
        "age_days": result.age_days,
        "event_id": result.event_id,
        "blocks_dispatch": result.blocks_dispatch,
        "reward_eligible": result.reward_eligible,
    }


def _pre_dispatch_task_dict(task) -> dict:
    return {
        "id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "assignee_user_id": task.assignee_user_id,
        "due_at": task.due_at.isoformat() if task.due_at else None,
    }


def _capability_dict(
    item: CompanyLeadCapability,
    *,
    company_name: str | None = None,
    company_code: str | None = None,
) -> dict:
    result = {
        "id": item.id,
        "company_id": item.company_id,
        "capability_code": item.capability_code,
        "active": item.active,
        "review_status": item.review_status,
        "review_note": item.review_note,
        "reviewed_by": item.reviewed_by,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }
    if company_name is not None:
        result["company_name"] = company_name
    if company_code is not None:
        result["company_code"] = company_code
    return result


def _area_dict(
    item: CompanyServiceAreaV12,
    *,
    company_name: str | None = None,
    company_code: str | None = None,
) -> dict:
    region = region_by_code(item.region_code)
    region_name = None
    if region is not None:
        region_name = " · ".join(
            part for part in (region["city_name"], region["district_name"]) if part
        )
    result = {
        "id": item.id,
        "company_id": item.company_id,
        "region_code": item.region_code,
        "region_name": region_name,
        "region_level": item.region_level,
        "is_primary_city": item.is_primary_city,
        "active": item.active,
        "review_status": item.review_status,
        "review_note": item.review_note,
        "reviewed_by": item.reviewed_by,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }
    if company_name is not None:
        result["company_name"] = company_name
    if company_code is not None:
        result["company_code"] = company_code
    return result


def _platform_lead_or_raise(db: Session, lead_id: str) -> Lead:
    lead = get_lead_or_404(db, lead_id)
    if lead.source_kind != LeadSourceKind.PLATFORM_MANUAL.value:
        raise AppError("LEAD_SOURCE_INVALID", "仅平台来源客资可从此入口查看", 409)
    return lead


@router.post("/platform/leads")
def create_platform_lead(
    body: LeadDraftBody,
    request: Request,
    principal=Depends(require_permissions("lead.manual.manage")),
    db: Session = Depends(get_db),
):
    lead = create_draft(
        db,
        principal=principal,
        source_kind=LeadSourceKind.PLATFORM_MANUAL,
        values=body.model_dump(exclude_none=True),
    )
    write_audit(
        db,
        principal=principal,
        action="V12_PLATFORM_LEAD_DRAFT_CREATE",
        resource_type="lead",
        resource_id=lead.id,
        after={"status": lead.status, "source_kind": lead.source_kind},
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, lead_supply_to_dict(lead, principal), "客资草稿已创建")


@router.patch("/platform/leads/{lead_id}")
def update_platform_lead(
    lead_id: str,
    body: LeadDraftUpdateBody,
    request: Request,
    principal=Depends(require_permissions("lead.manual.manage")),
    db: Session = Depends(get_db),
):
    lead = _platform_lead_or_raise(db, lead_id)
    before = lead_supply_to_dict(lead, principal)
    update_draft(db, lead=lead, principal=principal, values=body.model_dump(exclude_unset=True))
    write_audit(
        db,
        principal=principal,
        action="V12_PLATFORM_LEAD_DRAFT_UPDATE",
        resource_type="lead",
        resource_id=lead.id,
        before=before,
        after=lead_supply_to_dict(lead, principal),
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, lead_supply_to_dict(lead, principal))


@router.get("/platform/leads/{lead_id}")
def get_platform_lead(
    lead_id: str,
    request: Request,
    principal=Depends(require_permissions("lead.manual.manage")),
    db: Session = Depends(get_db),
):
    lead = _platform_lead_or_raise(db, lead_id)
    return ok(request, lead_supply_to_dict(lead, principal))


@router.post("/platform/leads/{lead_id}/submit")
def submit_platform_lead(
    lead_id: str,
    request: Request,
    principal=Depends(require_permissions("lead.manual.manage")),
    db: Session = Depends(get_db),
):
    lead = _platform_lead_or_raise(db, lead_id)
    result = submit_draft(db, lead=lead, principal=principal)
    write_audit(
        db,
        principal=principal,
        action="V12_PLATFORM_LEAD_SUBMIT",
        resource_type="lead",
        resource_id=lead.id,
        after={"status": lead.status, "duplicate_status": lead.duplicate_status},
        reason=result.decision.value,
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, {"lead": lead_supply_to_dict(lead, principal), "dedup": _dedup_dict(result)}, "客资已提交")


@router.get("/platform/leads")
def list_platform_leads(
    request: Request,
    principal=Depends(require_permissions("lead.manual.manage")),
    db: Session = Depends(get_db),
    status: str | None = Query(default=None),
    page_no: int = Query(default=1, alias="page", ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    stmt = select(Lead).where(Lead.source_kind == LeadSourceKind.PLATFORM_MANUAL.value)
    count_stmt = select(func.count(Lead.id)).where(Lead.source_kind == LeadSourceKind.PLATFORM_MANUAL.value)
    if status:
        stmt = stmt.where(Lead.status == status)
        count_stmt = count_stmt.where(Lead.status == status)
    total = db.scalar(count_stmt) or 0
    items = db.scalars(stmt.order_by(Lead.created_at.desc()).offset((page_no - 1) * page_size).limit(page_size)).all()
    return ok(request, page([lead_supply_to_dict(item, principal) for item in items], total, page_no, page_size))


@router.post("/supplier/leads")
def create_supplier_lead(
    body: LeadDraftBody,
    request: Request,
    principal=Depends(require_permissions("supplier.lead.manage")),
    db: Session = Depends(get_db),
):
    lead = create_draft(
        db,
        principal=principal,
        source_kind=LeadSourceKind.SUPPLIER_H5,
        values=body.model_dump(exclude_none=True),
    )
    write_audit(
        db,
        principal=principal,
        action="V12_SUPPLIER_LEAD_DRAFT_CREATE",
        resource_type="lead",
        resource_id=lead.id,
        after={"company_id": principal.company_id, "status": lead.status},
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, lead_supply_to_dict(lead, principal), "供应商客资草稿已创建")


@router.patch("/supplier/leads/{lead_id}")
def update_supplier_lead(
    lead_id: str,
    body: LeadDraftUpdateBody,
    request: Request,
    principal=Depends(require_permissions("supplier.lead.manage")),
    db: Session = Depends(get_db),
):
    lead = get_lead_or_404(db, lead_id)
    before = lead_supply_to_dict(lead, principal)
    update_draft(db, lead=lead, principal=principal, values=body.model_dump(exclude_unset=True))
    write_audit(
        db,
        principal=principal,
        action="V12_SUPPLIER_LEAD_DRAFT_UPDATE",
        resource_type="lead",
        resource_id=lead.id,
        before=before,
        after=lead_supply_to_dict(lead, principal),
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, lead_supply_to_dict(lead, principal))


@router.delete("/supplier/leads/{lead_id}")
def delete_supplier_lead_draft(
    lead_id: str,
    request: Request,
    principal=Depends(require_permissions("supplier.lead.manage")),
    db: Session = Depends(get_db),
):
    lead = get_lead_or_404(db, lead_id)
    before = lead_supply_to_dict(lead, principal)
    discard_draft(db, lead=lead, principal=principal)
    write_audit(
        db,
        principal=principal,
        action="V12_SUPPLIER_LEAD_DRAFT_DELETE",
        resource_type="lead",
        resource_id=lead_id,
        company_id=principal.company_id,
        before=before,
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, {"id": lead_id}, "草稿已删除")


@router.post("/supplier/leads/{lead_id}/revise")
def revise_rejected_supplier_lead(
    lead_id: str,
    request: Request,
    principal=Depends(require_permissions("supplier.lead.manage")),
    db: Session = Depends(get_db),
):
    lead = get_lead_or_404(db, lead_id)
    before = lead_supply_to_dict(lead, principal)
    reopen_rejected_supplier_lead(db, lead=lead, principal=principal)
    write_audit(
        db,
        principal=principal,
        action="V12_SUPPLIER_LEAD_REVISE",
        resource_type="lead",
        resource_id=lead.id,
        company_id=principal.company_id,
        before=before,
        after=lead_supply_to_dict(lead, principal),
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, lead_supply_to_dict(lead, principal), "请修改后重新提交")


@router.post("/supplier/leads/{lead_id}/submit")
def submit_supplier_lead(
    lead_id: str,
    request: Request,
    principal=Depends(require_permissions("supplier.lead.manage")),
    db: Session = Depends(get_db),
):
    lead = get_lead_or_404(db, lead_id)
    result = submit_draft(db, lead=lead, principal=principal)
    write_audit(
        db,
        principal=principal,
        action="V12_SUPPLIER_LEAD_SUBMIT",
        resource_type="lead",
        resource_id=lead.id,
        after={
            "company_id": principal.company_id,
            "status": lead.status,
            "duplicate_status": lead.duplicate_status,
            "submission_snapshot": lead_supply_to_dict(lead, principal),
        },
        reason=result.decision.value,
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, {"lead": lead_supply_to_dict(lead, principal), "dedup": _dedup_dict(result)}, "供应商客资已提交")


@router.get("/supplier/leads")
def supplier_lead_list(
    request: Request,
    principal=Depends(require_permissions("supplier.lead.manage")),
    db: Session = Depends(get_db),
    status: str | None = Query(default=None),
    page_no: int = Query(default=1, alias="page", ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    require_active_company(db, principal.company_id)
    items, total = list_supplier_leads(
        db,
        company_id=principal.company_id or "",
        status=status,
        page_no=page_no,
        page_size=page_size,
        submitter_user_id=principal.user_id if principal.has_any_role("FRANCHISE_EMPLOYEE") else None,
    )
    return ok(request, page([lead_supply_to_dict(item, principal) for item in items], total, page_no, page_size))


@router.get("/supplier/leads/{lead_id}")
def supplier_lead_detail(
    lead_id: str,
    request: Request,
    principal=Depends(require_permissions("supplier.lead.manage")),
    db: Session = Depends(get_db),
):
    lead = get_lead_or_404(db, lead_id)
    if not principal.can("*") and lead.supplier_company_id != principal.company_id:
        raise AppError("FORBIDDEN", "无权查看其他公司的供应商客资", 403)
    if (
        principal.has_any_role("FRANCHISE_EMPLOYEE")
        and lead.submitter_user_id != principal.user_id
    ):
        raise AppError("SUPPLIER_LEAD_NOT_OWNED", "加盟商员工只能查看本人录入的客资", 403)
    return ok(request, lead_supply_to_dict(lead, principal))


@router.post("/admin/supplier-leads/{lead_id}/review")
def admin_review_supplier_lead(
    lead_id: str,
    body: SupplierReviewBody,
    request: Request,
    principal=Depends(require_permissions("lead.supplier.review")),
    db: Session = Depends(get_db),
):
    lead = get_lead_or_404(db, lead_id)
    before = lead_supply_to_dict(lead, principal)
    review_decision = {"APPROVE": "QUALIFIED", "REJECT": "INVALID"}.get(
        body.decision,
        body.decision,
    )
    requires_telesales = review_decision in {"QUALIFIED", "INFO_INCOMPLETE"}
    result = review_supplier_lead(
        db,
        lead=lead,
        reviewer=principal,
        decision="INFO_INCOMPLETE" if requires_telesales else review_decision,
        note=body.note,
    )
    task = None
    if requires_telesales:
        assignment = assign_pre_dispatch_task(
            db,
            lead_id=lead.id,
            assignee_user_id=body.assignee_user_id or "",
            assigned_by=principal.user_id,
            reason=body.pre_dispatch_reason or "",
            template_code=body.template_code,
        )
        task = assignment.task
    after = lead_supply_to_dict(lead, principal)
    after["review_decision"] = review_decision
    after["submission_snapshot"] = before
    write_audit(
        db,
        principal=principal,
        action="V12_SUPPLIER_LEAD_REVIEW",
        resource_type="lead",
        resource_id=lead.id,
        before=before,
        after=after,
        reason=body.note or review_decision,
        request_id=request.state.request_id,
    )
    if task is not None:
        write_audit(
            db,
            principal=principal,
            action="V12_PRE_DISPATCH_VERIFY_ASSIGN",
            resource_type="verification_task",
            resource_id=task.id,
            before=assignment.before,
            after=assignment.after,
            reason=body.pre_dispatch_reason,
            request_id=request.state.request_id,
        )
    db.commit()
    return ok(
        request,
        {
            "lead": lead_supply_to_dict(lead, principal),
            "dedup": _dedup_dict(result),
            "task": _pre_dispatch_task_dict(task) if task else None,
        },
        "已派发电销核实" if task is not None else "资料初审已完成",
    )


@router.post("/admin/leads/{lead_id}/dedup-override")
def admin_override_dedup(
    lead_id: str,
    body: DedupOverrideBody,
    request: Request,
    principal=Depends(require_permissions("lead.dedup.override")),
    db: Session = Depends(get_db),
):
    lead = get_lead_or_404(db, lead_id)
    before = lead_supply_to_dict(lead, principal)
    try:
        item = override_duplicate(
            db,
            lead=lead,
            event_id=body.event_id,
            reason=body.reason,
            approved_by=principal.user_id,
        )
    except ValueError as exc:
        raise AppError("DEDUP_OVERRIDE_INVALID", str(exc), 422) from exc
    write_audit(
        db,
        principal=principal,
        action="V12_DEDUP_OVERRIDE",
        resource_type="lead",
        resource_id=lead.id,
        before=before,
        after=lead_supply_to_dict(lead, principal),
        reason=body.reason,
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, {"override_id": item.id, "lead": lead_supply_to_dict(lead, principal)}, "去重覆盖已生效")


@router.get("/company/capabilities")
def own_capabilities(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
):
    company = require_active_company(db, principal.company_id)
    return ok(request, [_capability_dict(item) for item in list_capabilities(db, company.id)])


@router.post("/company/capabilities")
def request_own_capability(
    body: CapabilityRequestBody,
    request: Request,
    principal=Depends(require_permissions("company.profile.manage")),
    db: Session = Depends(get_db),
):
    company = require_active_company(db, principal.company_id)
    item = request_capability(db, company.id, body.capability_code)
    write_audit(
        db,
        principal=principal,
        action="V12_COMPANY_CAPABILITY_REQUEST",
        resource_type="company_lead_capability",
        resource_id=item.id,
        company_id=company.id,
        after=_capability_dict(item),
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, _capability_dict(item), "公司能力申请已提交")


@router.get("/company/service-areas")
def own_service_areas(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
):
    company = require_active_company(db, principal.company_id)
    return ok(request, [_area_dict(item) for item in list_service_areas(db, company.id)])


@router.put("/company/service-areas")
def replace_own_service_areas(
    body: ServiceAreaReplaceBody,
    request: Request,
    principal=Depends(require_permissions("company.profile.manage")),
    db: Session = Depends(get_db),
):
    company = require_active_company(db, principal.company_id)
    items = replace_service_areas(
        db,
        company_id=company.id,
        region_codes=body.region_codes,
        primary_city_code=body.primary_city_code,
    )
    write_audit(
        db,
        principal=principal,
        action="V12_COMPANY_SERVICE_AREAS_REPLACE",
        resource_type="company",
        resource_id=company.id,
        company_id=company.id,
        after={"region_codes": [item.region_code for item in items], "review_status": "PENDING"},
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, [_area_dict(item) for item in items], "服务区域已提交审核")


@router.get("/admin/company-capabilities")
def admin_capability_list(
    request: Request,
    principal=Depends(require_permissions("company.profile.review")),
    db: Session = Depends(get_db),
    review_status: str | None = Query(default="PENDING"),
    page_no: int = Query(default=1, alias="page", ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    filters = []
    if review_status:
        filters.append(CompanyLeadCapability.review_status == review_status.upper())
    total = db.scalar(select(func.count(CompanyLeadCapability.id)).where(*filters)) or 0
    rows = db.execute(
        select(CompanyLeadCapability, Company.name, Company.code)
        .join(Company, Company.id == CompanyLeadCapability.company_id)
        .where(*filters)
        .order_by(CompanyLeadCapability.created_at.desc())
        .offset((page_no - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        _capability_dict(item, company_name=company_name, company_code=company_code)
        for item, company_name, company_code in rows
    ]
    return ok(request, page(items, int(total), page_no, page_size))


@router.post("/admin/companies/{company_id}/capabilities/{capability_code}/review")
def admin_review_capability(
    company_id: str,
    capability_code: str,
    body: CapabilityReviewBody,
    request: Request,
    principal=Depends(require_permissions("company.profile.review")),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if company is None:
        raise AppError("COMPANY_NOT_FOUND", "公司不存在", 404)
    item = review_capability(
        db,
        company_id=company_id,
        capability_code=capability_code,
        approve=body.decision == "APPROVE",
        reviewed_by=principal.user_id,
        note=body.note,
    )
    write_audit(
        db,
        principal=principal,
        action="V12_COMPANY_CAPABILITY_REVIEW",
        resource_type="company_lead_capability",
        resource_id=item.id,
        company_id=company_id,
        after=_capability_dict(item, company_name=company.name, company_code=company.code),
        reason=body.note or body.decision,
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(
        request,
        _capability_dict(item, company_name=company.name, company_code=company.code),
        "公司能力审核已完成",
    )


@router.post("/admin/companies/{company_id}/profile/approve-pending")
def admin_approve_pending_company_profile(
    company_id: str,
    body: CompanyProfileBulkApproveBody,
    request: Request,
    principal=Depends(require_permissions("company.profile.review")),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if company is None:
        raise AppError("COMPANY_NOT_FOUND", "公司不存在", 404)
    capabilities, areas = approve_pending_profile(
        db,
        company_id=company_id,
        reviewed_by=principal.user_id,
        note=body.note,
    )
    capability_items = [
        _capability_dict(item, company_name=company.name, company_code=company.code)
        for item in capabilities
    ]
    area_items = [
        _area_dict(item, company_name=company.name, company_code=company.code)
        for item in areas
    ]
    for item in capability_items:
        write_audit(
            db,
            principal=principal,
            action="V12_COMPANY_CAPABILITY_REVIEW",
            resource_type="company_lead_capability",
            resource_id=item["id"],
            company_id=company_id,
            after=item,
            metadata={"bulk_profile_approval": True},
            reason=body.note or "APPROVE",
            request_id=request.state.request_id,
        )
    for item in area_items:
        write_audit(
            db,
            principal=principal,
            action="V12_COMPANY_SERVICE_AREA_REVIEW",
            resource_type="company_service_area_v12",
            resource_id=item["id"],
            company_id=company_id,
            after=item,
            metadata={"bulk_profile_approval": True},
            reason=body.note or "APPROVE",
            request_id=request.state.request_id,
        )
    write_audit(
        db,
        principal=principal,
        action="V12_COMPANY_PROFILE_BULK_APPROVE",
        resource_type="company",
        resource_id=company_id,
        company_id=company_id,
        after={
            "capability_codes": [item["capability_code"] for item in capability_items],
            "service_area_codes": [item["region_code"] for item in area_items],
        },
        reason=body.note or "APPROVE",
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(
        request,
        {"company_id": company_id, "capabilities": capability_items, "service_areas": area_items},
        "加盟商待开通申请已一次通过",
    )


@router.get("/admin/service-areas")
def admin_service_area_list(
    request: Request,
    principal=Depends(require_permissions("company.profile.review")),
    db: Session = Depends(get_db),
    review_status: str | None = Query(default="PENDING"),
    page_no: int = Query(default=1, alias="page", ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    filters = []
    if review_status:
        filters.append(CompanyServiceAreaV12.review_status == review_status.upper())
    total = db.scalar(select(func.count(CompanyServiceAreaV12.id)).where(*filters)) or 0
    rows = db.execute(
        select(CompanyServiceAreaV12, Company.name, Company.code)
        .join(Company, Company.id == CompanyServiceAreaV12.company_id)
        .where(*filters)
        .order_by(CompanyServiceAreaV12.created_at.desc())
        .offset((page_no - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        _area_dict(item, company_name=company_name, company_code=company_code)
        for item, company_name, company_code in rows
    ]
    return ok(request, page(items, int(total), page_no, page_size))


@router.post("/admin/service-areas/{area_id}/review")
def admin_review_area(
    area_id: str,
    body: ServiceAreaReviewBody,
    request: Request,
    principal=Depends(require_permissions("company.profile.review")),
    db: Session = Depends(get_db),
):
    area = db.get(CompanyServiceAreaV12, area_id)
    if area is None:
        raise AppError("SERVICE_AREA_NOT_FOUND", "服务区域申请不存在", 404)
    company = db.get(Company, area.company_id)
    if company is None:
        raise AppError("COMPANY_NOT_FOUND", "公司不存在", 404)
    removal_request = str(area.review_note or "").startswith("[REMOVE_REQUEST]")
    item = review_service_area(
        db,
        area_id=area_id,
        approve=body.decision == "APPROVE",
        reviewed_by=principal.user_id,
        note=body.note,
    )
    write_audit(
        db,
        principal=principal,
        action="V12_COMPANY_SERVICE_AREA_REVIEW",
        resource_type="company_service_area_v12",
        resource_id=item.id,
        company_id=item.company_id,
        after={
            **_area_dict(item, company_name=company.name, company_code=company.code),
            "request_type": "REMOVE" if removal_request else "OPEN",
        },
        reason=body.note or body.decision,
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(
        request,
        _area_dict(item, company_name=company.name, company_code=company.code),
        "服务区域审核已完成",
    )

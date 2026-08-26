from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..core.auth import CurrentPrincipal, require_permissions
from ..core.database import get_db
from ..core.errors import AppError
from ..core.models import Assignment, Company
from ..core.responses import ok, page
from ..schemas.company import CompanyCreateBody, CompanySimpleCreateBody, CompanyUpdateBody
from ..services.audit import write_audit
from ..services.company_service import company_to_dict, create_company, create_simple_company, update_company

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("")
def list_companies(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page_no: int = Query(default=1, alias="page", ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    if not (
        principal.can("company.read")
        or principal.can("company.account.manage")
        or principal.can("*")
    ):
        raise AppError("FORBIDDEN", "无权查看加盟商公司列表", 403)
    stmt = select(Company).options(selectinload(Company.service_regions), selectinload(Company.capabilities), selectinload(Company.points_account))
    count_stmt = select(func.count(Company.id))
    if keyword:
        stmt = stmt.where(Company.name.contains(keyword) | Company.code.contains(keyword))
        count_stmt = count_stmt.where(Company.name.contains(keyword) | Company.code.contains(keyword))
    if status:
        stmt = stmt.where(Company.status == status)
        count_stmt = count_stmt.where(Company.status == status)
    total = db.scalar(count_stmt) or 0
    items = db.scalars(stmt.order_by(Company.created_at.desc()).offset((page_no - 1) * page_size).limit(page_size)).all()
    include_finance = principal.can("points.read") or principal.can("*")
    include_assignment_summary = principal.can("assignment.read") or principal.can("*")
    summaries: dict[str, dict[str, object]] = {}
    if include_assignment_summary and items:
        counts = db.execute(
            select(Assignment.company_id, Assignment.status, func.count(Assignment.id))
            .where(Assignment.company_id.in_([company.id for company in items]))
            .group_by(Assignment.company_id, Assignment.status)
        ).all()
        for company_id, assignment_status, count in counts:
            summary = summaries.setdefault(company_id, {"total": 0, "by_status": {}})
            summary["total"] = int(summary["total"]) + int(count)
            summary["by_status"][str(assignment_status)] = int(count)

    payload = []
    for company in items:
        item = company_to_dict(company, include_finance=include_finance)
        if include_assignment_summary:
            item["assignment_summary"] = summaries.get(
                company.id,
                {"total": 0, "by_status": {}},
            )
        payload.append(item)
    return ok(request, page(payload, total, page_no, page_size))


@router.post("")
def create_company_endpoint(
    body: CompanyCreateBody,
    request: Request,
    principal=Depends(require_permissions("company.profile.review")),
    db: Session = Depends(get_db),
):
    company = create_company(db, body)
    write_audit(db, principal=principal, action="COMPANY_CREATE", resource_type="company", resource_id=company.id, company_id=company.id, after={"code": company.code, "name": company.name}, request_id=request.state.request_id)
    db.commit()
    db.refresh(company)
    return ok(request, {"id": company.id, "code": company.code, "name": company.name}, "创建成功")


@router.post("/simple")
def create_simple_company_endpoint(
    body: CompanySimpleCreateBody,
    request: Request,
    principal=Depends(require_permissions("company.profile.review")),
    db: Session = Depends(get_db),
):
    company, readiness = create_simple_company(db, body, approved_by=principal.user_id)
    write_audit(
        db,
        principal=principal,
        action="COMPANY_SIMPLE_CREATE",
        resource_type="company",
        resource_id=company.id,
        company_id=company.id,
        after={
            "code": company.code,
            "name": company.name,
            "primary_city_code": body.primary_city_code,
            "district_codes": body.district_codes,
            "serve_all_districts": body.serve_all_districts,
            "readiness": readiness,
        },
        request_id=request.state.request_id,
    )
    db.commit()
    db.refresh(company)
    return ok(
        request,
        {"id": company.id, "code": company.code, "name": company.name, "readiness": readiness},
        "创建成功",
    )


@router.patch("/{company_id}")
def update_company_endpoint(
    company_id: str,
    body: CompanyUpdateBody,
    request: Request,
    principal=Depends(require_permissions("company.profile.review")),
    db: Session = Depends(get_db),
):
    company = db.scalar(select(Company).options(selectinload(Company.members), selectinload(Company.service_regions), selectinload(Company.capabilities)).where(Company.id == company_id))
    if not company:
        raise AppError("COMPANY_NOT_FOUND", "加盟商公司不存在", 404)
    before = {
        "name": company.name,
        "owner_name": company.owner_name,
        "status": company.status,
        "level_code": company.level_code,
        "notes": company.notes,
    }
    update_company(db, company, body)
    write_audit(
        db,
        principal=principal,
        action="COMPANY_UPDATE",
        resource_type="company",
        resource_id=company.id,
        company_id=company.id,
        before=before,
        after={
            "name": company.name,
            "owner_name": company.owner_name,
            "status": company.status,
            "level_code": company.level_code,
            "notes": company.notes,
        },
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, {"id": company.id}, "更新成功")

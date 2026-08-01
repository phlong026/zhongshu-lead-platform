from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.auth import CurrentPrincipal, require_permissions
from ..core.database import get_db
from ..core.errors import AppError
from ..core.models import Company, Role, User
from ..core.responses import ok
from ..services.company_service import company_to_dict

router = APIRouter(prefix="/admin-meta", tags=["admin-meta"])


@router.get("/rbac-matrix")
def rbac_matrix(
    request: Request,
    principal=Depends(require_permissions("*")),
    db: Session = Depends(get_db),
):
    roles = db.scalars(select(Role).options(selectinload(Role.permissions)).order_by(Role.code)).all()
    return ok(
        request,
        [
            {
                "code": role.code,
                "name": role.name,
                "system_role": role.system_role,
                "permissions": [
                    {
                        "code": permission.code,
                        "module": permission.module,
                        "sensitive": permission.sensitive,
                    }
                    for permission in sorted(role.permissions, key=lambda item: item.code)
                ],
            }
            for role in roles
        ],
    )


@router.get("/telesales-users")
def telesales_users(
    request: Request,
    principal=Depends(require_permissions("verification.read")),
    db: Session = Depends(get_db),
):
    users = db.scalars(select(User).options(selectinload(User.roles)).order_by(User.display_name)).all()
    return ok(
        request,
        [
            {"id": user.id, "display_name": user.display_name, "username": user.username, "status": user.status}
            for user in users
            if user.status == "ACTIVE" and any(role.code == "TELESALES" for role in user.roles)
        ],
    )


@router.get("/companies/{company_id}")
def company_detail(
    company_id: str,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
):
    if not (principal.can("company.read") or principal.can("*")):
        raise AppError("FORBIDDEN", "无权查看加盟商公司详情", 403)
    company = db.scalar(
        select(Company)
        .options(
            selectinload(Company.service_regions),
            selectinload(Company.capabilities),
            selectinload(Company.points_account),
            selectinload(Company.members),
        )
        .where(Company.id == company_id)
    )
    if not company:
        raise AppError("COMPANY_NOT_FOUND", "加盟商公司不存在", 404)
    data = company_to_dict(company, include_finance=principal.can("points.read") or principal.can("*"))
    data["members"] = [
        {
            "id": member.id,
            "display_name": member.display_name,
            "status": member.status,
            "is_primary": member.id == company.primary_user_id,
        }
        for member in company.members
    ]
    return ok(request, data)

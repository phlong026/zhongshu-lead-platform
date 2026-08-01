from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.auth import require_permissions
from ..core.database import get_db
from ..core.models import Role, User, UserRole
from ..core.responses import ok
from ..services.audit import write_audit
from ..services.auth_service import create_internal_user

router = APIRouter(prefix="/users", tags=["users"])


class UserCreateBody(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=64)
    role_code: str
    company_id: str | None = None


@router.get("")
def list_users(request: Request, principal=Depends(require_permissions("*")), db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.created_at.desc()).limit(500)).all()
    return ok(request, [{"id": u.id, "username": u.username, "display_name": u.display_name, "status": u.status, "company_id": u.company_id, "roles": [r.code for r in u.roles]} for u in users])


@router.post("")
def create_user(body: UserCreateBody, request: Request, principal=Depends(require_permissions("*")), db: Session = Depends(get_db)):
    user = create_internal_user(db, username=body.username, password=body.password, display_name=body.display_name, role_code=body.role_code, company_id=body.company_id)
    write_audit(db, principal=principal, action="USER_CREATE", resource_type="user", resource_id=user.id, company_id=body.company_id, after={"username": body.username, "role": body.role_code}, request_id=request.state.request_id)
    db.commit()
    return ok(request, {"id": user.id})


@router.post("/{user_id}/disable")
def disable_user(user_id: str, request: Request, principal=Depends(require_permissions("*")), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user:
        user.status = "DISABLED"
        user.session_version += 1
        write_audit(db, principal=principal, action="USER_DISABLE", resource_type="user", resource_id=user.id, company_id=user.company_id, request_id=request.state.request_id)
        db.commit()
    return ok(request)

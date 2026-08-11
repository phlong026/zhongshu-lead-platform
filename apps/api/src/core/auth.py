from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Cookie, Depends, Header
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .errors import AppError
from .models import Company, Permission, Role, RolePermission, User, UserRole
from .security import decode_access_token


@dataclass(frozen=True)
class Principal:
    user_id: str
    display_name: str
    company_id: str | None
    role_codes: frozenset[str]
    permission_codes: frozenset[str]
    session_version: int

    def has_any_role(self, *codes: str) -> bool:
        return bool(self.role_codes.intersection(codes))

    def can(self, code: str) -> bool:
        return "*" in self.permission_codes or code in self.permission_codes


def _extract_token(authorization: str | None, access_token: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    if access_token:
        return access_token
    raise AppError("AUTH_REQUIRED", "请先登录", 401)


def get_valid_session_user(
    db: Session,
    user_id: str | None,
    session_version: int | None,
) -> User | None:
    """Return the user only when every global session invalidation rule passes."""

    if not user_id or session_version is None:
        return None
    user = db.get(User, user_id)
    if not user or user.status != "ACTIVE" or user.session_version != session_version:
        return None
    if user.company_id:
        company = db.get(Company, user.company_id)
        if not company or company.status != "ACTIVE":
            return None
    return user


def load_current_principal(
    db: Session,
    user_id: str | None,
    session_version: int | None,
) -> Principal | None:
    if not user_id or session_version is None:
        return None
    rows = db.execute(
        select(
            User,
            Company.status.label("company_status"),
            Role.code.label("role_code"),
            Permission.code.label("permission_code"),
        )
        .outerjoin(Company, Company.id == User.company_id)
        .outerjoin(UserRole, UserRole.user_id == User.id)
        .outerjoin(Role, Role.id == UserRole.role_id)
        .outerjoin(RolePermission, RolePermission.role_id == Role.id)
        .outerjoin(Permission, Permission.id == RolePermission.permission_id)
        .where(User.id == user_id)
    ).all()
    if not rows:
        return None
    user = rows[0][0]
    if user.status != "ACTIVE" or user.session_version != session_version:
        return None
    if user.company_id and rows[0].company_status != "ACTIVE":
        return None
    return Principal(
        user_id=user.id,
        display_name=user.display_name,
        company_id=user.company_id,
        role_codes=frozenset(row.role_code for row in rows if row.role_code),
        permission_codes=frozenset(row.permission_code for row in rows if row.permission_code),
        session_version=user.session_version,
    )


def get_current_principal(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
    access_token: Annotated[str | None, Cookie()] = None,
) -> Principal:
    token = _extract_token(authorization, access_token)
    try:
        payload = decode_access_token(token)
    except InvalidTokenError as exc:
        raise AppError("AUTH_INVALID", "登录状态无效或已过期", 401) from exc
    principal = load_current_principal(db, payload.get("sub"), payload.get("sv"))
    if principal is None:
        raise AppError("AUTH_INVALID", "账号、公司或会话已失效", 401)

    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def require_permissions(*permissions: str) -> Callable[[Principal], Principal]:
    def dependency(principal: CurrentPrincipal) -> Principal:
        missing = [code for code in permissions if not principal.can(code)]
        if missing:
            raise AppError("FORBIDDEN", "无权执行该操作", 403, {"missing_permissions": missing})
        return principal

    return dependency


def require_roles(*roles: str) -> Callable[[Principal], Principal]:
    def dependency(principal: CurrentPrincipal) -> Principal:
        if not principal.has_any_role(*roles):
            raise AppError("FORBIDDEN", "当前角色无权访问", 403)
        return principal

    return dependency

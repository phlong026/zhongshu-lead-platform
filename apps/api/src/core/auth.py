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
    user = get_valid_session_user(db, payload.get("sub"), payload.get("sv"))
    if user is None:
        raise AppError("AUTH_INVALID", "账号、公司或会话已失效", 401)

    role_codes = set(
        db.scalars(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        ).all()
    )
    permission_codes = set(
        db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user.id)
        ).all()
    )
    return Principal(
        user_id=user.id,
        display_name=user.display_name,
        company_id=user.company_id,
        role_codes=frozenset(role_codes),
        permission_codes=frozenset(permission_codes),
        session_version=user.session_version,
    )


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

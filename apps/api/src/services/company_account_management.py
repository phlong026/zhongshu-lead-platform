from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.auth import Principal
from ..core.errors import AppError
from ..core.models import Company, Role, User
from ..core.role_contract import has_exactly_one_active_business_role
from ..core.security import hash_password, validate_internal_password
from .auth_service import create_internal_user
from .internal_user_management import generate_initial_password


COMPANY_ACCOUNT_ROLE_CODES = frozenset({"FRANCHISE_OWNER", "FRANCHISE_EMPLOYEE"})


def require_superadmin_reason(principal: Principal, reason: str | None) -> str | None:
    normalized = reason.strip() if reason else None
    if principal.has_any_role("SUPER_ADMIN") and not normalized:
        raise AppError(
            "SUPER_ADMIN_REASON_REQUIRED",
            "超级管理员执行加盟商账号操作时必须填写原因",
            422,
        )
    return normalized


def _company_or_raise(db: Session, company_id: str, *, lock: bool = False) -> Company:
    stmt = select(Company).where(Company.id == company_id)
    if lock:
        stmt = stmt.with_for_update()
    company = db.scalar(stmt)
    if company is None:
        raise AppError("COMPANY_NOT_FOUND", "加盟商公司不存在", 404)
    return company


def _account_role_codes(user: User) -> tuple[str, ...]:
    return tuple(sorted(role.code for role in user.roles))


def _is_company_account(user: User, company_id: str) -> bool:
    role_codes = _account_role_codes(user)
    return (
        user.company_id == company_id
        and has_exactly_one_active_business_role(role_codes)
        and role_codes[0] in COMPANY_ACCOUNT_ROLE_CODES
    )


def _load_company_account(db: Session, company_id: str, user_id: str, *, lock: bool = False) -> User:
    stmt = (
        select(User)
        .options(selectinload(User.roles), selectinload(User.wechat_identity))
        .where(User.id == user_id)
    )
    if lock:
        stmt = stmt.with_for_update(of=User)
    user = db.scalar(stmt)
    if user is None or not _is_company_account(user, company_id):
        raise AppError("COMPANY_ACCOUNT_NOT_FOUND", "加盟商账号不存在", 404)
    return user


def _has_active_owner(db: Session, company_id: str) -> bool:
    return bool(
        db.scalar(
            select(User.id)
            .join(User.roles)
            .where(
                User.company_id == company_id,
                User.status == "ACTIVE",
                Role.code == "FRANCHISE_OWNER",
            )
            .limit(1)
        )
    )


def company_account_to_dict(user: User) -> dict[str, object]:
    role_codes = _account_role_codes(user)
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "company_id": user.company_id,
        "role_code": role_codes[0] if len(role_codes) == 1 else None,
        "status": user.status,
        "wechat_bound": user.wechat_identity is not None,
        "session_version": user.session_version,
        "created_at": user.created_at.isoformat(),
    }


def list_company_accounts(db: Session, company_id: str) -> list[User]:
    _company_or_raise(db, company_id)
    users = db.scalars(
        select(User)
        .options(selectinload(User.roles), selectinload(User.wechat_identity))
        .join(User.roles)
        .where(
            User.company_id == company_id,
            Role.code.in_(COMPANY_ACCOUNT_ROLE_CODES),
        )
        .order_by(User.created_at.asc())
    ).unique().all()
    return [user for user in users if _is_company_account(user, company_id)]


def get_company_account(db: Session, company_id: str, user_id: str) -> User:
    """Load one company-scoped account for read-before-write response shaping."""

    return _load_company_account(db, company_id, user_id)


def create_company_account(
    db: Session,
    *,
    company_id: str,
    username: str,
    password: str,
    display_name: str,
    role_code: str,
) -> User:
    if role_code not in COMPANY_ACCOUNT_ROLE_CODES:
        raise AppError("COMPANY_ACCOUNT_ROLE_INVALID", "仅可创建加盟商负责人或员工账号", 422)
    company = _company_or_raise(db, company_id, lock=True)
    if company.status != "ACTIVE":
        raise AppError("COMPANY_DISABLED", "已停用的加盟商公司不能开通账号", 409)
    if role_code == "FRANCHISE_OWNER" and _has_active_owner(db, company_id):
        raise AppError("COMPANY_OWNER_EXISTS", "该加盟商已有启用中的负责人账号", 409)
    if role_code == "FRANCHISE_EMPLOYEE" and not _has_active_owner(db, company_id):
        raise AppError("COMPANY_OWNER_REQUIRED", "请先开通加盟商负责人账号", 409)
    if username != username.strip() or display_name != display_name.strip():
        raise AppError("COMPANY_ACCOUNT_IDENTITY_INVALID", "登录账号和显示名称首尾不能有空格", 422)
    try:
        validate_internal_password(password, username)
    except ValueError as exc:
        raise AppError("PASSWORD_POLICY_INVALID", str(exc), 400) from exc
    user = create_internal_user(
        db,
        username=username,
        password=password,
        display_name=display_name,
        role_code=role_code,
        company_id=company_id,
    )
    if role_code == "FRANCHISE_OWNER":
        company.primary_user_id = user.id
    db.flush()
    db.refresh(user, attribute_names=["roles", "wechat_identity"])
    return user


def set_company_account_status(
    db: Session,
    *,
    company_id: str,
    user_id: str,
    status: str,
) -> tuple[User, str, bool]:
    if status not in {"ACTIVE", "DISABLED"}:
        raise ValueError(f"unsupported company account status: {status}")
    company = _company_or_raise(db, company_id, lock=True)
    user = _load_company_account(db, company_id, user_id, lock=True)
    previous_status = user.status
    if previous_status == status:
        return user, previous_status, False
    if status == "DISABLED" and company.primary_user_id == user.id:
        raise AppError(
            "COMPANY_PRIMARY_ACCOUNT_PROTECTED",
            "请先完成负责人交接后再停用当前负责人账号",
            409,
        )
    if status == "DISABLED" and _account_role_codes(user) == ("FRANCHISE_EMPLOYEE",):
        from .company_assignment_v12 import has_active_internal_assignments

        if has_active_internal_assignments(db, company_id=company_id, user_id=user.id):
            raise AppError(
                "COMPANY_ACCOUNT_HANDOVER_REQUIRED",
                "该员工仍有进行中的内部客资，请先由负责人回收或转交",
                409,
            )
    user.status = status
    user.session_version += 1
    db.flush()
    return user, previous_status, True


def reset_company_account_password(
    db: Session,
    *,
    company_id: str,
    user_id: str,
    new_password: str,
) -> tuple[User, int]:
    user = _load_company_account(db, company_id, user_id, lock=True)
    if not user.username:
        raise AppError("COMPANY_ACCOUNT_PASSWORD_UNAVAILABLE", "微信绑定账号未设置登录账号，不能重置密码", 409)
    try:
        validate_internal_password(new_password, user.username)
    except ValueError as exc:
        raise AppError("PASSWORD_POLICY_INVALID", str(exc), 400) from exc
    previous_session_version = user.session_version
    user.password_hash = hash_password(new_password)
    user.session_version += 1
    db.flush()
    return user, previous_session_version


def initial_password_for_company_account(username: str, password: str | None) -> str:
    return password or generate_initial_password(username)

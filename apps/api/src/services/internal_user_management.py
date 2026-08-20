from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from ..core.errors import AppError
from ..core.models import Role, User
from ..core.security import hash_password, validate_internal_password
from .auth_service import create_internal_user
from .rbac import assign_role


INTERNAL_ROLE_CODES = frozenset(
    {
        "SUPER_ADMIN",
        "OWNER",
        "LEAD_ENTRY",
        "OPERATION",
        "TELESALES",
        "FINANCE",
        "RETURN_REVIEWER",
    }
)
_SUPERADMIN_LOCK_KEY = "zhongshu.internal-user.superadmin-roster"


def normalize_internal_roles(role_codes: list[str]) -> list[str]:
    normalized = sorted({code.strip() for code in role_codes if code.strip()})
    if not normalized:
        raise AppError("INTERNAL_ROLE_REQUIRED", "至少选择一个内部角色", 400)
    invalid = sorted(set(normalized) - INTERNAL_ROLE_CODES)
    if invalid:
        raise AppError(
            "INTERNAL_ROLE_INVALID",
            "包含不可分配的内部角色",
            400,
            {"invalid_role_codes": invalid},
        )
    return normalized


def validate_managed_password(password: str, username: str) -> None:
    try:
        validate_internal_password(password, username)
    except ValueError as exc:
        raise AppError("PASSWORD_POLICY_INVALID", str(exc), 400) from exc


def _validate_identity(username: str, display_name: str) -> tuple[str, str]:
    normalized_username = username.strip()
    normalized_display_name = display_name.strip()
    if normalized_username != username or normalized_display_name != display_name:
        raise AppError(
            "INTERNAL_IDENTITY_INVALID",
            "登录账号和显示名称首尾不能有空格",
            400,
        )
    return normalized_username, normalized_display_name


def _acquire_superadmin_roster_lock(db: Session) -> None:
    # PostgreSQL advisory locking serializes create/demote/disable decisions.
    # SQLite is used only by isolated tests and has no equivalent row-lock API.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": _SUPERADMIN_LOCK_KEY},
        )


def _is_internal_user(user: User) -> bool:
    role_codes = {role.code for role in user.roles}
    return bool(
        user.company_id is None
        and user.username
        and user.password_hash
        and user.wechat_identity is None
        and role_codes.issubset(INTERNAL_ROLE_CODES)
    )


def _load_internal_user(db: Session, user_id: str) -> User:
    user = db.scalar(
        select(User)
        .options(selectinload(User.roles), selectinload(User.wechat_identity))
        .where(User.id == user_id)
        .with_for_update(of=User)
    )
    if user is None:
        raise AppError("USER_NOT_FOUND", "账号不存在", 404)
    if not _is_internal_user(user):
        raise AppError(
            "INTERNAL_USER_REQUIRED",
            "该账号不属于平台内部账号管理范围",
            409,
        )
    return user


def _active_superadmins(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(User.roles)
            .where(
                Role.code == "SUPER_ADMIN",
                User.status == "ACTIVE",
                User.company_id.is_(None),
                User.username.is_not(None),
                User.password_hash.is_not(None),
                ~User.wechat_identity.has(),
                ~User.roles.any(Role.code.notin_(INTERNAL_ROLE_CODES)),
            )
            .order_by(User.id)
            .with_for_update(of=User)
        ).unique()
    )


def _protect_last_superadmin(db: Session, user: User) -> None:
    current_roles = {role.code for role in user.roles}
    if user.status != "ACTIVE" or "SUPER_ADMIN" not in current_roles:
        return
    active_superadmins = _active_superadmins(db)
    if len(active_superadmins) <= 1:
        raise AppError(
            "LAST_SUPER_ADMIN_REQUIRED",
            "必须保留至少一个启用中的超级管理员",
            409,
        )


def list_internal_users(db: Session) -> list[User]:
    users = db.scalars(
        select(User)
        .options(selectinload(User.roles), selectinload(User.wechat_identity))
        .where(
            User.company_id.is_(None),
            User.username.is_not(None),
            User.password_hash.is_not(None),
            ~User.wechat_identity.has(),
            ~User.roles.any(Role.code.notin_(INTERNAL_ROLE_CODES)),
        )
        .order_by(User.created_at.desc())
        .limit(500)
    ).all()
    return [user for user in users if _is_internal_user(user)]


def create_managed_internal_user(
    db: Session,
    *,
    username: str,
    password: str,
    display_name: str,
    role_codes: list[str],
    company_id: str | None,
) -> User:
    if company_id is not None:
        raise AppError(
            "INTERNAL_COMPANY_FORBIDDEN",
            "内部账号不能绑定加盟商公司",
            400,
        )
    normalized_username, normalized_display_name = _validate_identity(
        username,
        display_name,
    )
    roles = normalize_internal_roles(role_codes)
    validate_managed_password(password, normalized_username)
    if "SUPER_ADMIN" in roles:
        _acquire_superadmin_roster_lock(db)
    user = create_internal_user(
        db,
        username=normalized_username,
        password=password,
        display_name=normalized_display_name,
        role_code=roles[0],
    )
    for role_code in roles[1:]:
        assign_role(db, user, role_code)
    db.flush()
    db.refresh(user, attribute_names=["roles"])
    return user


def update_internal_roles(
    db: Session,
    *,
    user_id: str,
    role_codes: list[str],
) -> tuple[User, list[str], bool]:
    roles = normalize_internal_roles(role_codes)
    _acquire_superadmin_roster_lock(db)
    user = _load_internal_user(db, user_id)
    previous_roles = sorted(role.code for role in user.roles)
    if previous_roles == roles:
        return user, previous_roles, False
    if "SUPER_ADMIN" in previous_roles and "SUPER_ADMIN" not in roles:
        _protect_last_superadmin(db, user)

    role_rows = list(
        db.scalars(select(Role).where(Role.code.in_(roles)).order_by(Role.code)).all()
    )
    if len(role_rows) != len(roles):
        raise AppError("INTERNAL_ROLE_INVALID", "内部角色尚未初始化", 409)
    user.roles = role_rows
    user.session_version += 1
    db.flush()
    return user, previous_roles, True


def set_internal_user_status(
    db: Session,
    *,
    user_id: str,
    status: str,
) -> tuple[User, str, bool]:
    if status not in {"ACTIVE", "DISABLED"}:
        raise ValueError(f"unsupported internal user status: {status}")
    _acquire_superadmin_roster_lock(db)
    user = _load_internal_user(db, user_id)
    previous_status = user.status
    if previous_status == status:
        return user, previous_status, False
    if status == "DISABLED":
        _protect_last_superadmin(db, user)
    user.status = status
    user.session_version += 1
    db.flush()
    return user, previous_status, True


def reset_internal_password(
    db: Session,
    *,
    user_id: str,
    new_password: str,
) -> tuple[User, int]:
    user = _load_internal_user(db, user_id)
    validate_managed_password(new_password, user.username or "")
    previous_session_version = user.session_version
    user.password_hash = hash_password(new_password)
    user.session_version += 1
    db.flush()
    return user, previous_session_version

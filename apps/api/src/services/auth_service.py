from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..core.auth_models import AuthLoginState
from ..core.config import get_settings
from ..core.errors import AppError
from ..core.models import Company, InviteToken, User, WechatIdentity
from ..core.security import (
    create_access_token,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from ..core.time import as_utc, utcnow
from .rbac import assign_role

settings = get_settings()
_DUMMY_PASSWORD_HASH = hash_password("internal-login-timing-padding-value")


@dataclass(frozen=True)
class InternalAuthResult:
    user: User
    token: str
    lock_released: bool = False


class InternalAuthError(AppError):
    """Authentication error carrying server-only audit context."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        *,
        audit_action: str,
        user_id: str | None = None,
        failure_count: int | None = None,
        locked_until: datetime | None = None,
        lock_released: bool = False,
    ) -> None:
        super().__init__(code, message, status_code)
        self.audit_action = audit_action
        self.user_id = user_id
        self.failure_count = failure_count
        self.locked_until = locked_until
        self.lock_released = lock_released


def role_codes_for_user(user: User) -> list[str]:
    return sorted(role.code for role in user.roles)


def _new_login_state(db: Session, user_id: str) -> AuthLoginState:
    state = AuthLoginState(user_id=user_id, failed_count=0)
    db.add(state)
    db.flush()
    return state


def _clear_login_state(state: AuthLoginState) -> None:
    state.failed_count = 0
    state.last_failed_at = None
    state.locked_until = None


def _generic_login_error(
    *,
    audit_action: str,
    user_id: str | None = None,
    failure_count: int | None = None,
    locked_until: datetime | None = None,
    lock_released: bool = False,
) -> InternalAuthError:
    return InternalAuthError(
        "AUTH_LOGIN_FAILED",
        "用户名或密码错误",
        401,
        audit_action=audit_action,
        user_id=user_id,
        failure_count=failure_count,
        locked_until=locked_until,
        lock_released=lock_released,
    )


def _record_failed_attempt_sqlite(
    db: Session,
    *,
    user_id: str,
    now: datetime,
) -> tuple[int, datetime | None]:
    table = AuthLoginState.__table__
    window_start = now - timedelta(minutes=settings.login_failure_window_minutes)
    new_lock_until = now + timedelta(minutes=settings.login_lock_minutes)
    active_lock = and_(table.c.locked_until.is_not(None), table.c.locked_until > now)
    reset_window = or_(
        table.c.last_failed_at.is_(None),
        table.c.last_failed_at < window_start,
        and_(table.c.locked_until.is_not(None), table.c.locked_until <= now),
    )
    next_count = case(
        (active_lock, table.c.failed_count),
        (reset_window, 1),
        else_=table.c.failed_count + 1,
    )
    next_lock_until = case(
        (active_lock, table.c.locked_until),
        (next_count >= settings.login_max_failed_attempts, new_lock_until),
        else_=None,
    )
    initial_lock_until = new_lock_until if settings.login_max_failed_attempts <= 1 else None
    stmt = (
        sqlite_insert(AuthLoginState)
        .values(
            user_id=user_id,
            failed_count=1,
            last_failed_at=now,
            locked_until=initial_lock_until,
        )
        .on_conflict_do_update(
            index_elements=[AuthLoginState.user_id],
            set_={
                "failed_count": next_count,
                "last_failed_at": now,
                "locked_until": next_lock_until,
            },
        )
        .returning(AuthLoginState.failed_count, AuthLoginState.locked_until)
    )
    row = db.execute(stmt.execution_options(synchronize_session=False)).one()
    db.expire_all()
    return int(row.failed_count), as_utc(row.locked_until)


def authenticate_internal(db: Session, username: str, password: str) -> InternalAuthResult:
    now = utcnow()
    normalized_username = username.strip()
    user = db.scalar(select(User).where(User.username == normalized_username).with_for_update())
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        raise _generic_login_error(audit_action="AUTH_LOGIN_FAILED")

    state = db.get(AuthLoginState, user.id)
    locked_until = as_utc(state.locked_until) if state else None
    lock_released = bool(locked_until and locked_until <= now)
    if locked_until and locked_until > now:
        raise _generic_login_error(
            audit_action="AUTH_LOGIN_BLOCKED",
            user_id=user.id,
            failure_count=state.failed_count if state else 0,
            locked_until=locked_until,
        )

    last_failed_at = as_utc(state.last_failed_at) if state else None
    failure_window = timedelta(minutes=settings.login_failure_window_minutes)
    reset_state = bool(
        state
        and (
            lock_released
            or (last_failed_at and now - last_failed_at > failure_window)
        )
    )

    if not user.password_hash or not verify_password(password, user.password_hash):
        if db.get_bind().dialect.name == "sqlite":
            failure_count, next_locked_until = _record_failed_attempt_sqlite(
                db,
                user_id=user.id,
                now=now,
            )
        else:
            if state is None:
                state = _new_login_state(db, user.id)
            elif reset_state:
                _clear_login_state(state)
            state.failed_count += 1
            state.last_failed_at = now
            if state.failed_count >= settings.login_max_failed_attempts:
                state.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            failure_count = state.failed_count
            next_locked_until = as_utc(state.locked_until)

        if next_locked_until and next_locked_until > now and failure_count >= settings.login_max_failed_attempts:
            raise _generic_login_error(
                audit_action="AUTH_LOGIN_LOCKED",
                user_id=user.id,
                failure_count=failure_count,
                locked_until=next_locked_until,
                lock_released=lock_released,
            )
        raise _generic_login_error(
            audit_action="AUTH_LOGIN_FAILED",
            user_id=user.id,
            failure_count=failure_count,
            lock_released=lock_released,
        )

    if user.status != "ACTIVE":
        if state is not None and reset_state:
            _clear_login_state(state)
        raise _generic_login_error(
            audit_action="AUTH_LOGIN_BLOCKED",
            user_id=user.id,
            failure_count=state.failed_count if state else 0,
            lock_released=lock_released,
        )

    if state is not None:
        _clear_login_state(state)
    user.last_login_at = datetime.now(timezone.utc)
    roles = role_codes_for_user(user)
    token = create_access_token(user.id, user.session_version, roles, user.company_id)
    return InternalAuthResult(user=user, token=token, lock_released=lock_released)


def create_company_invite(db: Session, company_id: str, created_by: str | None, expires_hours: int) -> tuple[InviteToken, str]:
    company = db.get(Company, company_id)
    if not company or company.status == "DISABLED":
        raise AppError("COMPANY_NOT_AVAILABLE", "加盟商公司不存在或已停用", 404)
    raw = generate_token(32)
    invite = InviteToken(
        token_hash=hash_token(raw),
        company_id=company_id,
        created_by=created_by,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_hours),
    )
    db.add(invite)
    db.flush()
    return invite, raw


def _validate_invite(db: Session, raw_token: str) -> InviteToken:
    invite = db.scalar(select(InviteToken).where(InviteToken.token_hash == hash_token(raw_token)))
    now = utcnow()
    invite_expires_at = as_utc(invite.expires_at) if invite else None
    if not invite or invite.revoked_at or invite.used_at or not invite_expires_at or invite_expires_at <= now:
        raise AppError("AUTH_INVITE_INVALID", "邀请已失效，请联系平台", 400)
    company = db.get(Company, invite.company_id)
    if not company or company.status != "ACTIVE":
        raise AppError("AUTH_COMPANY_DISABLED", "加盟商公司不可用", 403)
    return invite


def _consume_invite(
    db: Session,
    raw_token: str,
    *,
    expected_company_id: str | None = None,
) -> InviteToken:
    """Atomically consume a one-time invite.

    The conditional UPDATE is the concurrency boundary for both PostgreSQL and
    SQLite. Exactly one transaction can transition used_at from NULL.
    """

    now = utcnow()
    filters = [
        InviteToken.token_hash == hash_token(raw_token),
        InviteToken.revoked_at.is_(None),
        InviteToken.used_at.is_(None),
        InviteToken.expires_at > now,
    ]
    if expected_company_id is not None:
        filters.append(InviteToken.company_id == expected_company_id)
    row = db.execute(
        update(InviteToken)
        .where(*filters)
        .values(used_at=now)
        .returning(InviteToken.id)
        .execution_options(synchronize_session=False)
    ).first()
    if row is None:
        raise AppError("AUTH_INVITE_INVALID", "邀请已失效，请联系平台", 400)
    db.expire_all()
    invite = db.get(InviteToken, row.id)
    if invite is None:
        raise AppError("AUTH_INVITE_INVALID", "邀请已失效，请联系平台", 400)
    company = db.get(Company, invite.company_id)
    if not company or company.status != "ACTIVE":
        raise AppError("AUTH_COMPANY_DISABLED", "加盟商公司不可用", 403)
    return invite


def login_or_bind_wechat(
    db: Session,
    *,
    openid: str,
    unionid: str | None = None,
    nickname: str | None = None,
    invite_token: str | None = None,
) -> tuple[User, str]:
    identity = db.scalar(select(WechatIdentity).where(WechatIdentity.openid == openid))
    if identity:
        user = db.get(User, identity.user_id)
        if not user or user.status != "ACTIVE":
            raise AppError("AUTH_ACCOUNT_DISABLED", "账号已停用", 403)
        company = db.get(Company, user.company_id) if user.company_id else None
        if not company or company.status != "ACTIVE":
            raise AppError("AUTH_COMPANY_DISABLED", "加盟商公司不可用", 403)
        if invite_token:
            invite = _validate_invite(db, invite_token)
            if invite.company_id != company.id:
                raise AppError("AUTH_WECHAT_BOUND_OTHER_COMPANY", "该微信已绑定其他加盟商公司", 409)
            _consume_invite(db, invite_token, expected_company_id=company.id)
        identity.unionid = unionid or identity.unionid
        identity.nickname = nickname or identity.nickname
        user.last_login_at = utcnow()
        token = create_access_token(user.id, user.session_version, role_codes_for_user(user), company.id)
        return user, token

    if not invite_token:
        raise AppError("AUTH_WECHAT_NOT_BOUND", "该微信尚未绑定加盟商，请使用邀请链接进入", 403)
    invite = _consume_invite(db, invite_token)
    company = db.get(Company, invite.company_id)
    assert company is not None
    user = User(
        display_name=nickname or company.owner_name or "加盟商负责人",
        company_id=company.id,
        status="ACTIVE",
        last_login_at=utcnow(),
    )
    db.add(user)
    db.flush()
    assign_role(db, user, "FRANCHISE_OWNER")
    db.add(WechatIdentity(openid=openid, unionid=unionid, nickname=nickname, user_id=user.id, subscribed=False))
    company.primary_user_id = user.id
    db.flush()
    token = create_access_token(user.id, user.session_version, role_codes_for_user(user), company.id)
    return user, token


def bind_wechat_by_invite(db: Session, raw_token: str, openid: str, nickname: str) -> tuple[User, str]:
    return login_or_bind_wechat(db, openid=openid, nickname=nickname, invite_token=raw_token)


def create_internal_user(
    db: Session,
    *,
    username: str,
    password: str,
    display_name: str,
    role_code: str,
    company_id: str | None = None,
) -> User:
    if db.scalar(select(User).where(User.username == username)):
        raise AppError("USER_EXISTS", "账号已存在", 409)
    user = User(
        username=username,
        password_hash=hash_password(password),
        display_name=display_name,
        company_id=company_id,
        status="ACTIVE",
    )
    db.add(user)
    db.flush()
    assign_role(db, user, role_code)
    return user

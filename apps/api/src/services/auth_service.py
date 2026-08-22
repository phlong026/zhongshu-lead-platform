from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..core.auth_models import AuthLoginState
from ..core.config import get_settings
from ..core.errors import AppError
from ..core.models import User
from ..core.security import (
    create_access_token,
    hash_password,
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


# Transitional internal adapters keep historical tests importable while they
# are migrated. They never accept a raw invitation token as proof of consent:
# the second argument is validated as a signed confirmation intent by the new
# binding service. These adapters are removed once the test suite no longer
# references the legacy names.
def create_company_invite(
    db: Session,
    company_id: str,
    created_by: str | None,
    expires_hours: int,
):
    from .invite_binding_service import create_company_invite as create_invite

    result = create_invite(db, company_id, created_by, expires_hours)
    return result.invite, result.raw_token


def bind_wechat_by_invite(
    db: Session,
    confirmation_intent: str,
    openid: str,
    display_name: str | None = None,
):
    from .invite_binding_service import bind_wechat_with_confirmation

    user, token, _ = bind_wechat_with_confirmation(
        db,
        confirmation_intent,
        openid=openid,
        nickname=display_name,
    )
    return user, token


def login_or_bind_wechat(
    db: Session,
    *,
    openid: str,
    unionid: str | None = None,
    nickname: str | None = None,
    avatar_url: str | None = None,
    subscribed: bool = False,
    invite_token: str | None = None,
):
    from .invite_binding_service import (
        bind_wechat_with_confirmation,
        login_bound_wechat,
    )

    if invite_token:
        user, token, _ = bind_wechat_with_confirmation(
            db,
            invite_token,
            openid=openid,
            unionid=unionid,
            nickname=nickname,
            avatar_url=avatar_url,
            subscribed=subscribed,
        )
        return user, token
    return login_bound_wechat(
        db,
        openid=openid,
        unionid=unionid,
        nickname=nickname,
        avatar_url=avatar_url,
        subscribed=subscribed,
    )

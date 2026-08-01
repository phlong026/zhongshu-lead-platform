from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

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


def role_codes_for_user(user: User) -> list[str]:
    return sorted(role.code for role in user.roles)


def authenticate_internal(db: Session, username: str, password: str) -> tuple[User, str]:
    user = db.scalar(select(User).where(User.username == username))
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        raise AppError("AUTH_LOGIN_FAILED", "用户名或密码错误", 401)
    if user.status != "ACTIVE":
        raise AppError("AUTH_ACCOUNT_DISABLED", "账号已停用", 403)
    user.last_login_at = datetime.now(timezone.utc)
    roles = role_codes_for_user(user)
    token = create_access_token(user.id, user.session_version, roles, user.company_id)
    return user, token


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


def bind_wechat_by_invite(db: Session, raw_token: str, openid: str, nickname: str) -> tuple[User, str]:
    invite = db.scalar(select(InviteToken).where(InviteToken.token_hash == hash_token(raw_token)))
    now = utcnow()
    invite_expires_at = as_utc(invite.expires_at) if invite else None
    if not invite or invite.revoked_at or invite.used_at or not invite_expires_at or invite_expires_at <= now:
        raise AppError("AUTH_INVITE_INVALID", "邀请已失效，请联系平台", 400)
    company = db.get(Company, invite.company_id)
    if not company or company.status != "ACTIVE":
        raise AppError("AUTH_COMPANY_DISABLED", "加盟商公司不可用", 403)

    identity = db.scalar(select(WechatIdentity).where(WechatIdentity.openid == openid))
    if identity:
        existing_user = db.get(User, identity.user_id)
        if existing_user and existing_user.company_id != company.id:
            raise AppError("AUTH_WECHAT_BOUND_OTHER_COMPANY", "该微信已绑定其他加盟商公司", 409)
        user = existing_user
    else:
        user = User(display_name=nickname or company.owner_name or "加盟商负责人", company_id=company.id, status="ACTIVE")
        db.add(user)
        db.flush()
        assign_role(db, user, "FRANCHISE_OWNER")
        identity = WechatIdentity(openid=openid, nickname=nickname, user_id=user.id, subscribed=False)
        db.add(identity)

    if not user:
        raise AppError("AUTH_BIND_FAILED", "绑定失败", 500)
    user.company_id = company.id
    user.session_version += 1
    company.primary_user_id = user.id
    invite.used_at = now
    db.flush()
    token = create_access_token(user.id, user.session_version, role_codes_for_user(user), company.id)
    return user, token


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

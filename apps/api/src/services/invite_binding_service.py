from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

from jwt import InvalidTokenError
from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.orm import Session, aliased

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.invite_models import (
    InviteBindingProfile,
    InviteConfirmationIntent,
    InviteMatchAttempt,
)
from ..core.models import (
    Company,
    CompanyCapability,
    CompanyServiceRegion,
    InviteToken,
    User,
    WechatIdentity,
    uuid_str,
)
from ..core.security import (
    create_access_token,
    create_signed_state,
    decode_signed_state,
    decrypt_text,
    encrypt_text,
    generate_token,
    hash_phone,
    hash_token,
)
from ..core.time import as_utc, utcnow
from .auth_service import role_codes_for_user
from .rbac import assign_role

settings = get_settings()

OWNER_NAME_FALLBACK = "该公司负责人"
CONFIRMATION_ROW_PURPOSE = "invite-binding-confirmation"
CONFIRMATION_TOKEN_PURPOSE = "invite-binding-confirmation"
OAUTH_BIND_STATE_PURPOSE = "wechat-oauth-bind"
CONFIRMATION_TTL_MINUTES = 10


@dataclass(frozen=True, slots=True)
class InviteCreationResult:
    invite: InviteToken
    profile: InviteBindingProfile
    raw_token: str
    invite_url: str
    copy_text: str
    company_name: str
    owner_name: str
    expires_at: datetime
    status: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class ConfirmationStartResult:
    intent_id: str
    confirmation_intent: str
    oauth_state: str
    expires_at: datetime
    return_url: str
    nonce_for_test: str


@dataclass(frozen=True, slots=True)
class InviteMaterial:
    invite_id: str
    company_id: str
    company_name: str
    owner_name: str
    invite_url: str
    copy_text: str
    expires_at: datetime
    status: str


def _safe_return_url(value: str | None) -> str:
    candidate = (value or "/h5/#/home").strip()
    if not candidate.startswith("/") or candidate.startswith("//") or len(candidate) > 512:
        return "/h5/#/home"
    return candidate


def _owner_name(value: str | None) -> str:
    normalized = (value or "").strip()
    return normalized or OWNER_NAME_FALLBACK


def _invite_url(raw_token: str) -> str:
    base = settings.app_base_url.rstrip("/")
    return f"{base}/h5/#/login?invite={quote(raw_token, safe='')}"


def _copy_text(owner_name: str, company_name: str, invite_url: str) -> str:
    return (
        f"{owner_name}您好，平台邀请您绑定“{company_name}”负责人账号。\n"
        f"请使用本人微信打开以下专属链接，核对公司信息并确认绑定：\n{invite_url}"
    )


def invite_status(invite: InviteToken, *, now: datetime | None = None) -> str:
    moment = now or utcnow()
    if invite.used_at is not None:
        return "USED"
    if invite.revoked_at is not None:
        return "REVOKED"
    expires_at = as_utc(invite.expires_at)
    if not expires_at or expires_at <= moment:
        return "EXPIRED"
    return "ACTIVE"


def _raise_invite_status(status: str) -> None:
    mapping = {
        "USED": ("AUTH_INVITE_USED", "邀请已使用，请联系平台重新获取", 410),
        "REVOKED": ("AUTH_INVITE_REVOKED", "邀请已撤销，请联系平台重新获取", 410),
        "EXPIRED": ("AUTH_INVITE_EXPIRED", "邀请已过期，请联系平台重新获取", 410),
    }
    if status in mapping:
        raise AppError(*mapping[status])


def _active_company_or_error(company: Company | None) -> Company:
    if company is None or company.status != "ACTIVE":
        raise AppError("AUTH_COMPANY_UNAVAILABLE", "加盟商公司当前不可用", 403)
    return company


def _ensure_company_unbound(company: Company) -> None:
    if company.primary_user_id:
        raise AppError("AUTH_COMPANY_ALREADY_BOUND", "该公司已有主账号，不能重复绑定", 409)


def _lookup_invite_by_raw_token(db: Session, raw_token: str) -> InviteToken:
    normalized = raw_token.strip()
    if len(normalized) < 16:
        raise AppError("AUTH_INVITE_INVALID", "邀请链接无效", 400)
    invite = db.scalar(
        select(InviteToken).where(InviteToken.token_hash == hash_token(normalized))
    )
    if invite is None:
        raise AppError("AUTH_INVITE_INVALID", "邀请链接无效", 400)
    _raise_invite_status(invite_status(invite))
    company = _active_company_or_error(db.get(Company, invite.company_id))
    _ensure_company_unbound(company)
    return invite


def _profile_for_invite(
    db: Session,
    invite: InviteToken,
    company: Company,
    *,
    raw_token: str | None = None,
    create_if_missing: bool = False,
) -> InviteBindingProfile | None:
    profile = db.get(InviteBindingProfile, invite.id)
    if profile is not None:
        return profile
    if not create_if_missing or raw_token is None:
        return None
    profile = InviteBindingProfile(
        invite_id=invite.id,
        company_id=company.id,
        company_name_snapshot=company.name,
        owner_name_snapshot=company.owner_name,
        token_encrypted=encrypt_text(raw_token),
        target_phone_hash=company.contact_phone_hash,
    )
    db.add(profile)
    db.flush()
    return profile


def get_company_invite_preflight(db: Session, company_id: str) -> dict[str, Any]:
    company = _active_company_or_error(db.get(Company, company_id))
    now = utcnow()
    active = db.scalar(
        select(InviteToken)
        .where(
            InviteToken.company_id == company.id,
            InviteToken.used_at.is_(None),
            InviteToken.revoked_at.is_(None),
            InviteToken.expires_at > now,
        )
        .order_by(InviteToken.created_at.desc())
        .limit(1)
    )
    return {
        "company_id": company.id,
        "company_name": company.name,
        "owner_name": _owner_name(company.owner_name),
        "company_status": company.status,
        "has_primary_user": bool(company.primary_user_id),
        "has_active_invite": active is not None,
        "active_invite_id": active.id if active else None,
        "active_invite_expires_at": as_utc(active.expires_at).isoformat() if active else None,
    }


def create_company_invite(
    db: Session,
    company_id: str,
    created_by: str | None,
    expires_hours: int,
) -> InviteCreationResult:
    if not 1 <= int(expires_hours) <= 168:
        raise AppError("AUTH_INVITE_EXPIRY_INVALID", "邀请有效期必须为 1 至 168 小时", 422)

    company = db.scalar(
        select(Company).where(Company.id == company_id).with_for_update()
    )
    company = _active_company_or_error(company)
    _ensure_company_unbound(company)

    now = utcnow()
    db.execute(
        update(InviteToken)
        .where(
            InviteToken.company_id == company.id,
            InviteToken.used_at.is_(None),
            InviteToken.revoked_at.is_(None),
            InviteToken.expires_at > now,
        )
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )

    raw_token = generate_token(32)
    invite = InviteToken(
        token_hash=hash_token(raw_token),
        company_id=company.id,
        created_by=created_by,
        expires_at=now + timedelta(hours=int(expires_hours)),
    )
    db.add(invite)
    db.flush()
    profile = InviteBindingProfile(
        invite_id=invite.id,
        company_id=company.id,
        company_name_snapshot=company.name,
        owner_name_snapshot=company.owner_name,
        token_encrypted=encrypt_text(raw_token),
        target_phone_hash=company.contact_phone_hash,
    )
    db.add(profile)
    db.flush()

    owner_name = _owner_name(profile.owner_name_snapshot)
    url = _invite_url(raw_token)
    return InviteCreationResult(
        invite=invite,
        profile=profile,
        raw_token=raw_token,
        invite_url=url,
        copy_text=_copy_text(owner_name, profile.company_name_snapshot, url),
        company_name=profile.company_name_snapshot,
        owner_name=owner_name,
        expires_at=as_utc(invite.expires_at),
    )


def preview_company_invite(db: Session, raw_token: str) -> dict[str, Any]:
    invite = _lookup_invite_by_raw_token(db, raw_token)
    company = _active_company_or_error(db.get(Company, invite.company_id))
    profile = _profile_for_invite(db, invite, company)
    region_codes = list(
        db.scalars(
            select(CompanyServiceRegion.region_code)
            .where(
                CompanyServiceRegion.company_id == company.id,
                CompanyServiceRegion.active.is_(True),
            )
            .order_by(CompanyServiceRegion.region_code)
        ).all()
    )
    capability_codes = list(
        db.scalars(
            select(CompanyCapability.category_code)
            .where(
                CompanyCapability.company_id == company.id,
                CompanyCapability.active.is_(True),
            )
            .order_by(CompanyCapability.category_code)
        ).all()
    )
    return {
        "invite_id": invite.id,
        "company_id": company.id,
        "company_name": profile.company_name_snapshot if profile else company.name,
        "owner_name": _owner_name(profile.owner_name_snapshot if profile else company.owner_name),
        "region_codes": region_codes,
        "capability_codes": capability_codes,
        "level_code": company.level_code,
        "expires_at": as_utc(invite.expires_at).isoformat(),
        "status": "ACTIVE",
        "binding_explanation": "确认后将把当前微信绑定为该公司的唯一主账号。",
    }


def create_confirmation_intent(
    db: Session,
    raw_token: str,
    return_url: str | None,
) -> ConfirmationStartResult:
    invite = _lookup_invite_by_raw_token(db, raw_token)
    company = _active_company_or_error(db.get(Company, invite.company_id))
    _ensure_company_unbound(company)
    _profile_for_invite(
        db,
        invite,
        company,
        raw_token=raw_token,
        create_if_missing=True,
    )

    now = utcnow()
    expires_at = now + timedelta(minutes=CONFIRMATION_TTL_MINUTES)
    nonce = generate_token(24)
    row = InviteConfirmationIntent(
        invite_id=invite.id,
        company_id=company.id,
        purpose=CONFIRMATION_ROW_PURPOSE,
        nonce_hash=hash_token(nonce),
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    target = _safe_return_url(return_url)
    confirmation_intent = create_signed_state(
        {
            "intent_id": row.id,
            "nonce": nonce,
            "invite_id": invite.id,
            "company_id": company.id,
            "binding_confirmed": True,
            "return_url": target,
        },
        expires_minutes=CONFIRMATION_TTL_MINUTES,
        purpose=CONFIRMATION_TOKEN_PURPOSE,
    )
    oauth_state = create_signed_state(
        {
            "confirmation_intent": confirmation_intent,
            "return_url": target,
        },
        expires_minutes=CONFIRMATION_TTL_MINUTES,
        purpose=OAUTH_BIND_STATE_PURPOSE,
    )
    return ConfirmationStartResult(
        intent_id=row.id,
        confirmation_intent=confirmation_intent,
        oauth_state=oauth_state,
        expires_at=expires_at,
        return_url=target,
        nonce_for_test=nonce,
    )


def _decode_confirmation_carrier(carrier: str) -> tuple[dict[str, Any], str]:
    try:
        confirmation = decode_signed_state(
            carrier,
            purpose=CONFIRMATION_TOKEN_PURPOSE,
        )
        return confirmation, _safe_return_url(confirmation.get("return_url"))
    except InvalidTokenError:
        pass

    try:
        oauth_state = decode_signed_state(carrier, purpose=OAUTH_BIND_STATE_PURPOSE)
        nested = oauth_state.get("confirmation_intent")
        if not isinstance(nested, str) or not nested:
            raise InvalidTokenError("missing confirmation intent")
        confirmation = decode_signed_state(
            nested,
            purpose=CONFIRMATION_TOKEN_PURPOSE,
        )
        state_return = _safe_return_url(oauth_state.get("return_url"))
        confirm_return = _safe_return_url(confirmation.get("return_url"))
        if state_return != confirm_return:
            raise InvalidTokenError("return URL mismatch")
        return confirmation, state_return
    except InvalidTokenError as exc:
        raise AppError(
            "AUTH_CONFIRMATION_INTENT_INVALID",
            "绑定确认已失效，请重新打开邀请链接",
            400,
        ) from exc


def confirmation_return_url(carrier: str) -> str:
    _, target = _decode_confirmation_carrier(carrier)
    return target


def _validate_confirmation_row(
    db: Session,
    payload: dict[str, Any],
) -> InviteConfirmationIntent:
    required = {"intent_id", "nonce", "invite_id", "company_id", "binding_confirmed"}
    if not required.issubset(payload) or payload.get("binding_confirmed") is not True:
        raise AppError(
            "AUTH_CONFIRMATION_INTENT_INVALID",
            "绑定确认无效，请重新确认",
            400,
        )
    row = db.scalar(
        select(InviteConfirmationIntent)
        .where(InviteConfirmationIntent.id == str(payload["intent_id"]))
        .with_for_update()
    )
    if row is None or row.purpose != CONFIRMATION_ROW_PURPOSE:
        raise AppError(
            "AUTH_CONFIRMATION_INTENT_INVALID",
            "绑定确认无效，请重新确认",
            400,
        )
    if row.used_at is not None:
        raise AppError(
            "AUTH_CONFIRMATION_INTENT_USED",
            "该绑定确认已使用，请勿重复提交",
            409,
        )
    expires_at = as_utc(row.expires_at)
    if not expires_at or expires_at <= utcnow():
        raise AppError(
            "AUTH_CONFIRMATION_INTENT_EXPIRED",
            "绑定确认已过期，请重新确认",
            410,
        )
    if (
        row.invite_id != str(payload["invite_id"])
        or row.company_id != str(payload["company_id"])
        or row.nonce_hash != hash_token(str(payload["nonce"]))
    ):
        raise AppError(
            "AUTH_CONFIRMATION_INTENT_INVALID",
            "绑定确认校验失败",
            400,
        )
    return row


def _add_wechat_identity(
    db: Session,
    *,
    user_id: str,
    openid: str,
    unionid: str | None,
    nickname: str | None,
    avatar_url: str | None,
    subscribed: bool,
) -> WechatIdentity:
    identity = WechatIdentity(
        openid=openid,
        unionid=unionid,
        nickname=nickname,
        avatar_url=avatar_url,
        subscribed=subscribed,
        user_id=user_id,
    )
    db.add(identity)
    return identity


def _identity_for_wechat(
    db: Session,
    *,
    openid: str,
    unionid: str | None,
) -> WechatIdentity | None:
    filters = [WechatIdentity.openid == openid]
    if unionid:
        filters.append(WechatIdentity.unionid == unionid)
    return db.scalar(select(WechatIdentity).where(or_(*filters)).limit(1))


def bind_wechat_with_confirmation(
    db: Session,
    confirmation_carrier: str,
    *,
    openid: str,
    unionid: str | None = None,
    nickname: str | None = None,
    avatar_url: str | None = None,
    subscribed: bool = False,
) -> tuple[User, str, InviteToken]:
    payload, _ = _decode_confirmation_carrier(confirmation_carrier)
    company_id = str(payload.get("company_id") or "")
    invite_id = str(payload.get("invite_id") or "")

    company = db.scalar(
        select(Company).where(Company.id == company_id).with_for_update()
    )
    company = _active_company_or_error(company)
    intent = _validate_confirmation_row(db, payload)
    invite = db.scalar(
        select(InviteToken)
        .where(InviteToken.id == invite_id, InviteToken.company_id == company.id)
        .with_for_update()
    )
    if invite is None:
        raise AppError("AUTH_INVITE_INVALID", "邀请链接无效", 400)
    _raise_invite_status(invite_status(invite))
    _ensure_company_unbound(company)

    existing_identity = _identity_for_wechat(db, openid=openid, unionid=unionid)
    if existing_identity is not None:
        existing_user = db.get(User, existing_identity.user_id)
        if existing_user is None or existing_user.company_id != company.id:
            raise AppError(
                "AUTH_WECHAT_BOUND_OTHER_COMPANY",
                "该微信已绑定其他加盟商公司，系统不会自动覆盖",
                409,
            )
        raise AppError(
            "AUTH_COMPANY_ALREADY_BOUND",
            "该公司已有主账号，不能重复绑定",
            409,
        )

    user_id = uuid_str()
    occupied = db.execute(
        update(Company)
        .where(
            Company.id == company.id,
            Company.status == "ACTIVE",
            Company.primary_user_id.is_(None),
        )
        .values(primary_user_id=user_id)
        .returning(Company.id)
        .execution_options(synchronize_session=False)
    ).first()
    if occupied is None:
        db.expire(company)
        refreshed = db.get(Company, company.id)
        if refreshed is None or refreshed.status != "ACTIVE":
            raise AppError("AUTH_COMPANY_UNAVAILABLE", "加盟商公司当前不可用", 403)
        raise AppError("AUTH_COMPANY_ALREADY_BOUND", "该公司已有主账号，不能重复绑定", 409)

    user = User(
        id=user_id,
        display_name=nickname or company.owner_name or "微信加盟商",
        company_id=company.id,
        status="ACTIVE",
        last_login_at=utcnow(),
    )
    db.add(user)
    db.flush()
    assign_role(db, user, "FRANCHISE_OWNER")
    _add_wechat_identity(
        db,
        user_id=user.id,
        openid=openid,
        unionid=unionid,
        nickname=nickname,
        avatar_url=avatar_url,
        subscribed=subscribed,
    )
    db.flush()

    now = utcnow()
    intent_consumed = db.execute(
        update(InviteConfirmationIntent)
        .where(
            InviteConfirmationIntent.id == intent.id,
            InviteConfirmationIntent.invite_id == invite.id,
            InviteConfirmationIntent.company_id == company.id,
            InviteConfirmationIntent.used_at.is_(None),
            InviteConfirmationIntent.expires_at > now,
        )
        .values(used_at=now)
        .returning(InviteConfirmationIntent.id)
        .execution_options(synchronize_session=False)
    ).first()
    if intent_consumed is None:
        raise AppError(
            "AUTH_CONFIRMATION_INTENT_USED",
            "该绑定确认已使用或已过期",
            409,
        )

    invite_consumed = db.execute(
        update(InviteToken)
        .where(
            InviteToken.id == invite.id,
            InviteToken.company_id == company.id,
            InviteToken.used_at.is_(None),
            InviteToken.revoked_at.is_(None),
            InviteToken.expires_at > now,
        )
        .values(used_at=now)
        .returning(InviteToken.id)
        .execution_options(synchronize_session=False)
    ).first()
    if invite_consumed is None:
        raise AppError("AUTH_INVITE_INVALID", "邀请已失效，请重新获取", 409)

    profile = db.get(InviteBindingProfile, invite.id)
    if profile is None:
        raise AppError("AUTH_INVITE_PROFILE_MISSING", "邀请档案不完整，请重新生成邀请", 409)
    profile.bound_user_id = user.id
    profile.bound_at = now
    db.flush()
    db.refresh(invite)
    token = create_access_token(
        user.id,
        user.session_version,
        role_codes_for_user(user),
        company.id,
    )
    return user, token, invite


def login_bound_wechat(
    db: Session,
    *,
    openid: str,
    unionid: str | None = None,
    nickname: str | None = None,
    avatar_url: str | None = None,
    subscribed: bool = False,
) -> tuple[User, str]:
    identity = _identity_for_wechat(db, openid=openid, unionid=unionid)
    if identity is None:
        raise AppError(
            "AUTH_WECHAT_NOT_BOUND",
            "该微信尚未绑定加盟商，请使用专属邀请链接进入",
            403,
        )
    user = db.get(User, identity.user_id)
    if user is None or user.status != "ACTIVE":
        raise AppError("AUTH_ACCOUNT_DISABLED", "账号已停用", 403)
    company = _active_company_or_error(db.get(Company, user.company_id)) if user.company_id else None
    if company is None:
        raise AppError("AUTH_COMPANY_UNAVAILABLE", "加盟商公司当前不可用", 403)
    identity.unionid = unionid or identity.unionid
    identity.nickname = nickname or identity.nickname
    identity.avatar_url = avatar_url or identity.avatar_url
    identity.subscribed = subscribed or identity.subscribed
    user.last_login_at = utcnow()
    token = create_access_token(
        user.id,
        user.session_version,
        role_codes_for_user(user),
        company.id,
    )
    return user, token


def invitation_material(db: Session, invite_id: str) -> InviteMaterial:
    invite = db.get(InviteToken, invite_id)
    if invite is None:
        raise AppError("AUTH_INVITE_NOT_FOUND", "邀请记录不存在", 404)
    profile = db.get(InviteBindingProfile, invite.id)
    if profile is None:
        raise AppError("AUTH_INVITE_PROFILE_MISSING", "该历史邀请无法恢复链接", 409)
    raw_token = decrypt_text(profile.token_encrypted)
    if not raw_token or hash_token(raw_token) != invite.token_hash:
        raise AppError("AUTH_INVITE_PROFILE_INVALID", "邀请链接密文校验失败", 409)
    owner_name = _owner_name(profile.owner_name_snapshot)
    url = _invite_url(raw_token)
    return InviteMaterial(
        invite_id=invite.id,
        company_id=invite.company_id,
        company_name=profile.company_name_snapshot,
        owner_name=owner_name,
        invite_url=url,
        copy_text=_copy_text(owner_name, profile.company_name_snapshot, url),
        expires_at=as_utc(invite.expires_at),
        status=invite_status(invite),
    )


def _status_filter(status: str, now: datetime):
    normalized = status.strip().upper()
    if normalized == "ACTIVE":
        return and_(
            InviteToken.used_at.is_(None),
            InviteToken.revoked_at.is_(None),
            InviteToken.expires_at > now,
        )
    if normalized == "USED":
        return InviteToken.used_at.is_not(None)
    if normalized == "REVOKED":
        return and_(
            InviteToken.used_at.is_(None),
            InviteToken.revoked_at.is_not(None),
        )
    if normalized == "EXPIRED":
        return and_(
            InviteToken.used_at.is_(None),
            InviteToken.revoked_at.is_(None),
            InviteToken.expires_at <= now,
        )
    raise AppError("AUTH_INVITE_STATUS_INVALID", "邀请状态筛选值无效", 422)


def list_invites(
    db: Session,
    *,
    company_id: str | None = None,
    status: str | None = None,
    created_by: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page_no: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    if page_no < 1 or not 1 <= page_size <= 100:
        raise AppError("PAGINATION_INVALID", "分页参数无效", 422)
    creator = aliased(User)
    bound_user = aliased(User)
    filters: list[Any] = []
    now = utcnow()
    if company_id:
        filters.append(InviteToken.company_id == company_id)
    if status:
        filters.append(_status_filter(status, now))
    if created_by:
        filters.append(InviteToken.created_by == created_by)
    if created_from:
        filters.append(InviteToken.created_at >= created_from)
    if created_to:
        filters.append(InviteToken.created_at <= created_to)

    total = db.scalar(select(func.count(InviteToken.id)).where(*filters)) or 0
    rows = db.execute(
        select(
            InviteToken,
            InviteBindingProfile,
            Company.name.label("current_company_name"),
            creator.display_name.label("creator_name"),
            bound_user.display_name.label("bound_user_name"),
        )
        .join(Company, Company.id == InviteToken.company_id)
        .outerjoin(
            InviteBindingProfile,
            InviteBindingProfile.invite_id == InviteToken.id,
        )
        .outerjoin(creator, creator.id == InviteToken.created_by)
        .outerjoin(bound_user, bound_user.id == InviteBindingProfile.bound_user_id)
        .where(*filters)
        .order_by(InviteToken.created_at.desc(), InviteToken.id.desc())
        .offset((page_no - 1) * page_size)
        .limit(page_size)
    ).all()
    items = []
    for invite, profile, current_company_name, creator_name, bound_user_name in rows:
        items.append(
            {
                "invite_id": invite.id,
                "created_at": as_utc(invite.created_at).isoformat(),
                "created_by": invite.created_by,
                "created_by_name": creator_name or "系统",
                "company_id": invite.company_id,
                "company_name": profile.company_name_snapshot if profile else current_company_name,
                "owner_name": _owner_name(profile.owner_name_snapshot if profile else None),
                "expires_at": as_utc(invite.expires_at).isoformat(),
                "used_at": as_utc(invite.used_at).isoformat() if invite.used_at else None,
                "revoked_at": as_utc(invite.revoked_at).isoformat() if invite.revoked_at else None,
                "bound_user_id": profile.bound_user_id if profile else None,
                "bound_user_name": bound_user_name,
                "bound_at": as_utc(profile.bound_at).isoformat() if profile and profile.bound_at else None,
                "match_source": profile.match_source if profile else None,
                "status": invite_status(invite, now=now),
            }
        )
    return items, int(total)


def get_invite_detail(db: Session, invite_id: str) -> dict[str, Any]:
    items, _ = list_invites(db, page_no=1, page_size=100)
    for item in items:
        if item["invite_id"] == invite_id:
            if item["status"] == "ACTIVE":
                material = invitation_material(db, invite_id)
                item = {
                    **item,
                    "invite_url": material.invite_url,
                    "copy_text": material.copy_text,
                }
            return item
    if db.get(InviteToken, invite_id) is None:
        raise AppError("AUTH_INVITE_NOT_FOUND", "邀请记录不存在", 404)
    invite = db.get(InviteToken, invite_id)
    items, _ = list_invites(
        db,
        company_id=invite.company_id,
        page_no=1,
        page_size=100,
    )
    return next(item for item in items if item["invite_id"] == invite_id)


def revoke_invite(db: Session, invite_id: str) -> InviteToken:
    invite = db.scalar(
        select(InviteToken).where(InviteToken.id == invite_id).with_for_update()
    )
    if invite is None:
        raise AppError("AUTH_INVITE_NOT_FOUND", "邀请记录不存在", 404)
    status = invite_status(invite)
    if status == "USED":
        raise AppError("AUTH_INVITE_USED", "已使用邀请不能撤销", 409)
    if status == "EXPIRED":
        raise AppError("AUTH_INVITE_EXPIRED", "已过期邀请不能撤销", 409)
    if status == "ACTIVE":
        invite.revoked_at = utcnow()
        db.flush()
    return invite


def _company_summary(company: Company) -> dict[str, Any]:
    return {
        "id": company.id,
        "code": company.code,
        "name": company.name,
        "owner_name": _owner_name(company.owner_name),
        "status": company.status,
        "level_code": company.level_code,
        "has_primary_user": bool(company.primary_user_id),
    }


def match_company_by_phone(
    db: Session,
    phone: str,
    *,
    requested_by: str | None = None,
) -> dict[str, Any]:
    fingerprint = hash_phone(phone)
    companies = list(
        db.scalars(
            select(Company)
            .where(Company.contact_phone_hash == fingerprint)
            .order_by(Company.id)
        ).all()
    )
    active = [company for company in companies if company.status == "ACTIVE"]
    selectable = [company for company in active if not company.primary_user_id]
    if len(selectable) == 1:
        outcome = "UNIQUE"
        selected = selectable[0]
    elif len(selectable) > 1:
        outcome = "MULTIPLE"
        selected = None
    elif active and all(company.primary_user_id for company in active):
        outcome = "ALREADY_BOUND"
        selected = None
    elif companies:
        outcome = "COMPANY_DISABLED"
        selected = None
    else:
        outcome = "NONE"
        selected = None
    db.add(
        InviteMatchAttempt(
            source="WECHAT_AUTHORIZED_MOBILE",
            requested_by=requested_by,
            phone_hash=fingerprint,
            selected_company_id=selected.id if selected else None,
            candidate_count=len(selectable),
            outcome=outcome,
        )
    )
    db.flush()
    return {
        "outcome": outcome,
        "company": _company_summary(selected) if selected else None,
        "candidates": [_company_summary(company) for company in selectable]
        if outcome == "MULTIPLE"
        else [],
    }


def manual_match_companies(
    db: Session,
    *,
    query: str | None = None,
    region_code: str | None = None,
    page_no: int = 1,
    page_size: int = 20,
    requested_by: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    if page_no < 1 or not 1 <= page_size <= 100:
        raise AppError("PAGINATION_INVALID", "分页参数无效", 422)
    filters: list[Any] = [
        Company.status == "ACTIVE",
        Company.primary_user_id.is_(None),
    ]
    normalized_query = (query or "").strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        filters.append(
            or_(
                Company.name.ilike(pattern),
                Company.code.ilike(pattern),
                Company.owner_name.ilike(pattern),
            )
        )
    if region_code:
        filters.append(
            exists(
                select(CompanyServiceRegion.id).where(
                    CompanyServiceRegion.company_id == Company.id,
                    CompanyServiceRegion.region_code == region_code,
                    CompanyServiceRegion.active.is_(True),
                )
            )
        )
    total = db.scalar(select(func.count(Company.id)).where(*filters)) or 0
    companies = list(
        db.scalars(
            select(Company)
            .where(*filters)
            .order_by(Company.name, Company.id)
            .offset((page_no - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    db.add(
        InviteMatchAttempt(
            source="MANUAL_SEARCH",
            requested_by=requested_by,
            query_text=normalized_query or None,
            region_code=region_code,
            candidate_count=int(total),
            outcome="FOUND" if total else "NONE",
        )
    )
    db.flush()
    return [_company_summary(company) for company in companies], int(total)


def confirm_manual_match(
    db: Session,
    company_id: str,
    *,
    requested_by: str | None,
    source: str = "MANUAL_CONFIRM",
) -> dict[str, Any]:
    company = db.scalar(
        select(Company).where(Company.id == company_id).with_for_update()
    )
    company = _active_company_or_error(company)
    _ensure_company_unbound(company)
    attempt = InviteMatchAttempt(
        source=source,
        requested_by=requested_by,
        selected_company_id=company.id,
        candidate_count=1,
        outcome="CONFIRMED",
        confirmed_at=utcnow(),
    )
    db.add(attempt)
    db.flush()
    return {"match_id": attempt.id, "company": _company_summary(company)}

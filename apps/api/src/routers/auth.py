from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from ..core.auth import CurrentPrincipal, require_permissions
from ..core.config import get_settings
from ..core.database import get_db
from ..core.models import Company, InviteToken, User
from ..core.responses import ok
from ..core.security import create_signed_state, decode_signed_state
from ..schemas.auth import InviteConfirmStartBody, InviteCreateBody, LoginBody, WechatMockCallbackBody
from ..services.audit import write_audit
from ..services.auth_service import (
    InternalAuthError,
    authenticate_internal,
    build_invite_copy_text,
    create_company_invite,
    login_or_bind_wechat,
    validate_invite,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _request_ip(request: Request) -> str | None:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


def _audit_unlock(db: Session, *, user_id: str | None, request: Request) -> None:
    if not user_id:
        return
    write_audit(
        db,
        principal=None,
        action="AUTH_LOGIN_UNLOCKED",
        resource_type="user",
        resource_id=user_id,
        metadata={"reason_code": "LOCK_EXPIRED"},
        request_id=request.state.request_id,
        ip_address=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=settings.app_env.lower() == "production",
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )


def _resolve_binding_intent(state: str) -> tuple[str | None, str | None, str]:
    """Decode a signed OAuth state and split binding intents from legacy login states.

    Returns (invite_id, expected_company_id, return_url). Binding intents
    (purpose="wechat-oauth-bind") require an explicit binding_confirmed flag;
    legacy states only permit login of already-bound identities and never
    carry an invite reference.
    """

    from jwt import InvalidTokenError

    from ..core.errors import AppError

    try:
        bind_state = decode_signed_state(state, purpose="wechat-oauth-bind")
    except InvalidTokenError:
        bind_state = None
    if bind_state is not None:
        if bind_state.get("binding_confirmed") is not True:
            raise AppError("AUTH_BINDING_CONFIRM_REQUIRED", "请先在邀请页确认后继续", 400)
        invite_id = bind_state.get("invite_id")
        company_id = bind_state.get("company_id")
        if not invite_id or not company_id:
            raise AppError("AUTH_OAUTH_STATE_INVALID", "微信授权状态已失效，请重新进入", 400)
        return str(invite_id), str(company_id), str(bind_state.get("return_url") or "/h5/#/home")
    try:
        legacy_state = decode_signed_state(state, purpose="wechat-oauth")
    except InvalidTokenError as exc:
        raise AppError("AUTH_OAUTH_STATE_INVALID", "微信授权状态已失效，请重新进入", 400) from exc
    # legacy purpose 状态不再携带邀请：未绑定微信必须先走确认后授权流程
    return None, None, str(legacy_state.get("return_url") or "/h5/#/home")


def _sanitize_return_url(value: str) -> str:
    """Constrain return_url to a same-origin path.

    Browsers treat backslashes like slashes for special schemes, so a value
    like "/\\evil.com" is parsed as "//evil.com" and must be rejected too.
    """
    if not value.startswith("/") or value.startswith(("//", "/\\", "\\")):
        return "/h5/#/home"
    return value


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]):
    try:
        result = authenticate_internal(db, body.username, body.password)
    except InternalAuthError as exc:
        if exc.lock_released:
            _audit_unlock(db, user_id=exc.user_id, request=request)
        write_audit(
            db,
            principal=None,
            action=exc.audit_action,
            resource_type="user",
            resource_id=exc.user_id,
            metadata={
                "reason_code": exc.code,
                "failure_count": exc.failure_count,
                "locked_until": exc.locked_until.isoformat() if exc.locked_until else None,
            },
            request_id=request.state.request_id,
            ip_address=_request_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        # Authentication failure state is security data and must survive the error response.
        db.commit()
        raise

    user = result.user
    if result.lock_released:
        _audit_unlock(db, user_id=user.id, request=request)
    write_audit(
        db,
        principal=None,
        action="AUTH_LOGIN",
        resource_type="user",
        resource_id=user.id,
        request_id=request.state.request_id,
        ip_address=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    _set_session_cookie(response, result.token)
    return ok(
        request,
        {
            "user": {
                "id": user.id,
                "display_name": user.display_name,
                "roles": [r.code for r in user.roles],
            }
        },
    )


@router.post("/logout")
def logout(request: Request, response: Response, principal: CurrentPrincipal, db: Annotated[Session, Depends(get_db)]):
    user = db.get(User, principal.user_id)
    if user:
        user.session_version += 1
    write_audit(db, principal=principal, action="AUTH_LOGOUT", resource_type="user", resource_id=principal.user_id, request_id=request.state.request_id)
    db.commit()
    response.delete_cookie(
        "access_token",
        path="/",
        secure=settings.app_env.lower() == "production",
        httponly=True,
        samesite="lax",
    )
    return ok(request, message="已退出")


@router.get("/me")
def me(request: Request, principal: CurrentPrincipal):
    return ok(
        request,
        {
            "id": principal.user_id,
            "display_name": principal.display_name,
            "company_id": principal.company_id,
            "roles": sorted(principal.role_codes),
            "permissions": sorted(principal.permission_codes),
        },
    )


@router.post("/companies/{company_id}/invites")
def create_invite(
    company_id: str,
    body: InviteCreateBody,
    request: Request,
    principal=Depends(require_permissions("*")),
    db: Session = Depends(get_db),
):
    invite, raw, superseded_ids = create_company_invite(db, company_id, principal.user_id, body.expires_hours)
    write_audit(db, principal=principal, action="INVITE_CREATE", resource_type="invite", resource_id=invite.id, company_id=company_id, request_id=request.state.request_id)
    if superseded_ids:
        # 只记录被撤销邀请的 id，绝不落任何 token 原文或文案
        write_audit(
            db,
            principal=principal,
            action="INVITE_AUTO_REVOKE",
            resource_type="invite",
            resource_id=invite.id,
            company_id=company_id,
            metadata={"superseded_invite_ids": superseded_ids, "reason": "superseded_by_new_invite"},
            request_id=request.state.request_id,
        )
    db.commit()
    company = db.get(Company, company_id)
    assert company is not None
    url = f"{settings.app_base_url}/h5/#/login?invite={raw}"
    expires_at = invite.expires_at.isoformat()
    return ok(
        request,
        {
            "invite_id": invite.id,
            "token": raw,
            "url": url,
            "company_name": company.name,
            "owner_name": company.owner_name,
            "copy_text": build_invite_copy_text(company.owner_name, company.name, url, expires_at),
            "expires_at": expires_at,
            "revoked_invite_count": len(superseded_ids),
        },
    )


@router.post("/invites/confirm-start")
def invite_confirm_start(
    body: InviteConfirmStartBody,
    request: Request,
    db: Session = Depends(get_db),
):
    """Exchange a confirmed invite for a short-lived binding OAuth intent (P0-04)."""

    from ..integrations.wechat import WechatOAuthClient

    invite = validate_invite(db, raw_token=body.invite)
    return_url = _sanitize_return_url(body.return_url)
    state = create_signed_state(
        {
            "invite_id": invite.id,
            "company_id": invite.company_id,
            "binding_confirmed": True,
            "return_url": return_url,
        },
        purpose="wechat-oauth-bind",
    )
    write_audit(
        db,
        principal=None,
        action="INVITE_CONFIRM_START",
        resource_type="invite",
        resource_id=invite.id,
        company_id=invite.company_id,
        request_id=request.state.request_id,
    )
    db.commit()
    payload = decode_signed_state(state, purpose="wechat-oauth-bind")
    expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
    return ok(
        request,
        {
            "authorization_url": WechatOAuthClient().authorization_url(state=state),
            "expires_at": expires_at.isoformat(),
        },
    )


@router.post("/invites/{invite_id}/revoke")
def revoke_invite(
    invite_id: str,
    request: Request,
    principal=Depends(require_permissions("*")),
    db: Session = Depends(get_db),
):
    invite = db.get(InviteToken, invite_id)
    if invite:
        invite.revoked_at = datetime.now(timezone.utc)
        write_audit(db, principal=principal, action="INVITE_REVOKE", resource_type="invite", resource_id=invite.id, company_id=invite.company_id, request_id=request.state.request_id)
        db.commit()
    return ok(request, message="邀请已撤销")


@router.post("/wechat/mock-callback")
def wechat_mock_callback(body: WechatMockCallbackBody, request: Request, response: Response, db: Session = Depends(get_db)):
    from ..core.errors import AppError

    if not settings.wechat_dev_mock:
        raise AppError("AUTH_MOCK_DISABLED", "开发模拟登录已关闭", 403)
    # mock 通道与生产回调同一合同：绑定必须携带确认后的 signed state（P0-07）
    invite_id, expected_company_id, _ = _resolve_binding_intent(body.state)
    user, token = login_or_bind_wechat(
        db,
        openid=body.openid,
        nickname=body.nickname,
        invite_id=invite_id,
        expected_company_id=expected_company_id,
    )
    write_audit(db, principal=None, action="WECHAT_BIND", resource_type="user", resource_id=user.id, company_id=user.company_id, request_id=request.state.request_id)
    db.commit()
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax", max_age=settings.jwt_expire_minutes * 60, path="/")
    return ok(request, {"token": token, "user_id": user.id, "company_id": user.company_id})


@router.get("/wechat/start")
def wechat_start(
    request: Request,
    return_url: str = Query(default="/h5/#/home"),
):
    from fastapi.responses import RedirectResponse

    from ..core.errors import AppError
    from ..integrations.wechat import WechatOAuthClient

    # Phase 3.5/H2：旧邀请入口显式拒绝。只删参数声明时 FastAPI 会忽略
    # 未声明的 query 参数并返回 200，旧链接会静默走完一次微信跳转。
    # 首次绑定必须经 /auth/invites/confirm-start 取得确认后的 signed state。
    if "invite" in request.query_params:
        raise AppError("AUTH_INVITE_ENTRY_DEPRECATED", "邀请入口已更新，请从最新邀请链接重新进入", 400)
    return_url = _sanitize_return_url(return_url)
    state = create_signed_state({"return_url": return_url}, purpose="wechat-oauth")
    return RedirectResponse(url=WechatOAuthClient().authorization_url(state=state), status_code=302)


@router.get("/wechat/callback")
def wechat_callback(
    code: str,
    state: str,
    request: Request,
    db: Session = Depends(get_db),
):
    from fastapi.responses import RedirectResponse
    from ..integrations.wechat import WechatOAuthClient

    invite_id, expected_company_id, return_url = _resolve_binding_intent(state)
    identity = WechatOAuthClient().exchange_code(code)
    user, token = login_or_bind_wechat(
        db,
        openid=identity.openid,
        unionid=identity.unionid,
        nickname=identity.nickname or "微信加盟商",
        invite_id=invite_id,
        expected_company_id=expected_company_id,
    )
    write_audit(db, principal=None, action="WECHAT_OAUTH_LOGIN", resource_type="user", resource_id=user.id, company_id=user.company_id, request_id=request.state.request_id)
    db.commit()
    response = RedirectResponse(url=return_url, status_code=302)
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=settings.app_env.lower() == "production",
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )
    return response

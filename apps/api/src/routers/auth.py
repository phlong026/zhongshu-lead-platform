from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.auth import CurrentPrincipal, require_permissions
from ..core.config import get_settings
from ..core.database import get_db
from ..core.models import Company, InviteToken, User
from ..core.responses import ok
from ..core.security import create_signed_state, decode_signed_state, hash_token
from ..core.time import as_utc, utcnow
from ..schemas.auth import InviteCreateBody, LoginBody, WechatMockCallbackBody
from ..services.audit import write_audit
from ..services.auth_service import authenticate_internal, bind_wechat_by_invite, create_company_invite

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]):
    user, token = authenticate_internal(db, body.username, body.password)
    write_audit(db, principal=None, action="AUTH_LOGIN", resource_type="user", resource_id=user.id, request_id=request.state.request_id)
    db.commit()
    response.set_cookie("access_token", token, httponly=True, secure=settings.app_env == "production", samesite="lax", max_age=settings.jwt_expire_minutes * 60)
    return ok(request, {"token": token, "user": {"id": user.id, "display_name": user.display_name, "roles": [r.code for r in user.roles]}})


@router.post("/logout")
def logout(request: Request, response: Response, principal: CurrentPrincipal, db: Annotated[Session, Depends(get_db)]):
    user = db.get(User, principal.user_id)
    if user:
        user.session_version += 1
    write_audit(db, principal=principal, action="AUTH_LOGOUT", resource_type="user", resource_id=principal.user_id, request_id=request.state.request_id)
    db.commit()
    response.delete_cookie("access_token")
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
    invite, raw = create_company_invite(db, company_id, principal.user_id, body.expires_hours)
    write_audit(db, principal=principal, action="INVITE_CREATE", resource_type="invite", resource_id=invite.id, company_id=company_id, request_id=request.state.request_id)
    db.commit()
    return ok(request, {"invite_id": invite.id, "token": raw, "url": f"{settings.app_base_url}/h5/#/login?invite={raw}", "expires_at": invite.expires_at.isoformat()})


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
    if not settings.wechat_dev_mock:
        from ..core.errors import AppError
        raise AppError("AUTH_MOCK_DISABLED", "开发模拟登录已关闭", 403)
    user, token = bind_wechat_by_invite(db, body.invite_token, body.openid, body.nickname)
    write_audit(db, principal=None, action="WECHAT_BIND", resource_type="user", resource_id=user.id, company_id=user.company_id, request_id=request.state.request_id)
    db.commit()
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax", max_age=settings.jwt_expire_minutes * 60)
    return ok(request, {"token": token, "user_id": user.id, "company_id": user.company_id})


@router.get("/wechat/start")
def wechat_start(
    invite: str = Query(min_length=16),
    return_url: str = Query(default="/h5/#/home"),
    db: Session = Depends(get_db),
):
    from fastapi.responses import RedirectResponse
    from ..integrations.wechat import WechatOAuthClient

    invite_row = db.scalar(select(InviteToken).where(InviteToken.token_hash == hash_token(invite)))
    now = utcnow()
    invite_expires_at = as_utc(invite_row.expires_at) if invite_row else None
    if not invite_row or invite_row.revoked_at or invite_row.used_at or not invite_expires_at or invite_expires_at <= now:
        from ..core.errors import AppError
        raise AppError("AUTH_INVITE_INVALID", "邀请已失效，请联系平台", 400)
    if not return_url.startswith("/") or return_url.startswith("//"):
        return_url = "/h5/#/home"
    state = create_signed_state({"invite": invite, "return_url": return_url}, purpose="wechat-oauth")
    url = WechatOAuthClient().authorization_url(state=state)
    return RedirectResponse(url=url, status_code=302)


@router.get("/wechat/callback")
def wechat_callback(
    code: str,
    state: str,
    request: Request,
    db: Session = Depends(get_db),
):
    from fastapi.responses import RedirectResponse
    from jwt import InvalidTokenError
    from ..core.errors import AppError
    from ..integrations.wechat import WechatOAuthClient

    try:
        state_data = decode_signed_state(state, purpose="wechat-oauth")
    except InvalidTokenError as exc:
        raise AppError("AUTH_OAUTH_STATE_INVALID", "微信授权状态已失效，请重新进入", 400) from exc
    identity = WechatOAuthClient().exchange_code(code)
    user, token = bind_wechat_by_invite(db, str(state_data["invite"]), identity.openid, identity.nickname or "微信加盟商")
    write_audit(db, principal=None, action="WECHAT_OAUTH_BIND", resource_type="user", resource_id=user.id, company_id=user.company_id, request_id=request.state.request_id)
    db.commit()
    target = str(state_data.get("return_url") or "/h5/#/home")
    response = RedirectResponse(url=target, status_code=302)
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
    )
    return response

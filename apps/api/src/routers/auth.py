from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from ..core.auth import CurrentPrincipal
from ..core.config import get_settings
from ..core.database import get_db
from ..core.errors import AppError
from ..core.models import User
from ..core.responses import ok
from ..core.security import create_signed_state, decode_signed_state
from ..integrations.wechat import WechatOAuthClient
from ..schemas.auth import LoginBody, WechatMockCallbackBody
from ..services.audit import write_audit
from ..services.auth_service import (
    InternalAuthError,
    authenticate_internal,
)
from ..services.invite_binding_service import (
    OAUTH_BIND_STATE_PURPOSE,
    bind_wechat_with_confirmation,
    confirmation_return_url,
    login_bound_wechat,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _request_ip(request: Request) -> str | None:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


def _safe_return_url(value: str | None) -> str:
    candidate = (value or "/h5/#/home").strip()
    if not candidate.startswith("/") or candidate.startswith("//") or len(candidate) > 512:
        return "/h5/#/home"
    return candidate


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


@router.post("/login")
def login(
    body: LoginBody,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
):
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
                "roles": [role.code for role in user.roles],
            }
        },
    )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    principal: CurrentPrincipal,
    db: Annotated[Session, Depends(get_db)],
):
    user = db.get(User, principal.user_id)
    if user:
        user.session_version += 1
    write_audit(
        db,
        principal=principal,
        action="AUTH_LOGOUT",
        resource_type="user",
        resource_id=principal.user_id,
        request_id=request.state.request_id,
    )
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


@router.post("/wechat/mock-callback")
def wechat_mock_callback(
    body: WechatMockCallbackBody,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
):
    if not settings.wechat_dev_mock:
        raise AppError("AUTH_MOCK_DISABLED", "开发模拟登录已关闭", 403)
    user, token, invite = bind_wechat_with_confirmation(
        db,
        body.confirmation_intent,
        openid=body.openid,
        unionid=body.unionid,
        nickname=body.nickname,
        avatar_url=body.avatar_url,
        subscribed=body.subscribed,
    )
    write_audit(
        db,
        principal=None,
        action="WECHAT_BIND",
        resource_type="user",
        resource_id=user.id,
        company_id=user.company_id,
        metadata={"invite_id": invite.id, "mode": "DEV_MOCK"},
        request_id=request.state.request_id,
    )
    db.commit()
    _set_session_cookie(response, token)
    return ok(
        request,
        {"user_id": user.id, "company_id": user.company_id},
        "微信主账号绑定成功",
    )


@router.get("/wechat/start")
def wechat_start(
    request: Request,
    return_url: str = Query(default="/h5/#/home"),
):
    # FastAPI ignores undeclared query parameters. Inspect the raw query map so
    # the retired URL cannot silently redirect and fail only at callback time.
    if "invite" in request.query_params:
        raise AppError(
            "AUTH_INVITE_ENTRY_DEPRECATED",
            "旧邀请入口已停用，请从最新邀请链接重新进入",
            400,
        )
    target = _safe_return_url(return_url)
    state = create_signed_state(
        {"return_url": target},
        purpose="wechat-oauth",
    )
    return RedirectResponse(
        url=WechatOAuthClient().authorization_url(state=state),
        status_code=302,
    )


@router.get("/wechat/callback")
def wechat_callback(
    code: str,
    state: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    client = WechatOAuthClient()
    binding_flow = False
    try:
        decode_signed_state(state, purpose=OAUTH_BIND_STATE_PURPOSE)
        binding_flow = True
    except InvalidTokenError:
        try:
            ordinary_state = decode_signed_state(state, purpose="wechat-oauth")
        except InvalidTokenError as exc:
            raise AppError(
                "AUTH_OAUTH_STATE_INVALID",
                "微信授权状态已失效，请重新进入",
                400,
            ) from exc

    identity = client.exchange_code(code)
    if binding_flow:
        user, token, invite = bind_wechat_with_confirmation(
            db,
            state,
            openid=identity.openid,
            unionid=identity.unionid,
            nickname=identity.nickname or "微信加盟商",
            avatar_url=getattr(identity, "avatar_url", None),
        )
        target = confirmation_return_url(state)
        action = "WECHAT_BIND"
        metadata = {"invite_id": invite.id, "mode": "OAUTH"}
    else:
        user, token = login_bound_wechat(
            db,
            openid=identity.openid,
            unionid=identity.unionid,
            nickname=identity.nickname,
            avatar_url=getattr(identity, "avatar_url", None),
        )
        target = _safe_return_url(ordinary_state.get("return_url"))
        action = "WECHAT_OAUTH_LOGIN"
        metadata = {"mode": "OAUTH"}

    write_audit(
        db,
        principal=None,
        action=action,
        resource_type="user",
        resource_id=user.id,
        company_id=user.company_id,
        metadata=metadata,
        request_id=request.state.request_id,
    )
    db.commit()
    response = RedirectResponse(url=target, status_code=302)
    _set_session_cookie(response, token)
    return response

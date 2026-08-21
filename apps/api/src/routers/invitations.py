from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..core.auth import require_permissions
from ..core.config import get_settings
from ..core.database import get_db
from ..core.errors import AppError
from ..core.responses import ok, page
from ..integrations.wechat import WechatOAuthClient
from ..schemas.auth import InviteCreateBody
from ..schemas.invite import (
    InviteConfirmStartBody,
    InviteDeliveryBody,
    InvitePreviewBody,
    ManualMatchConfirmBody,
    VerifiedPhoneMatchBody,
)
from ..services.audit import write_audit
from ..services.invite_binding_service import (
    confirm_manual_match,
    create_company_invite,
    create_confirmation_intent,
    get_company_invite_preflight,
    get_invite_detail,
    list_invites,
    manual_match_companies,
    match_company_by_phone,
    preview_company_invite,
    revoke_invite,
)
from ..services.invite_delivery import prepare_invite_delivery

router = APIRouter(prefix="/auth", tags=["invitations"])
settings = get_settings()


def _admin_principal():
    return Depends(require_permissions("*"))


@router.get("/companies/{company_id}/invites/preflight")
def invite_preflight(
    company_id: str,
    request: Request,
    principal=_admin_principal(),
    db: Session = Depends(get_db),
):
    return ok(request, get_company_invite_preflight(db, company_id))


@router.post("/companies/{company_id}/invites")
def create_invite(
    company_id: str,
    body: InviteCreateBody,
    request: Request,
    principal=_admin_principal(),
    db: Session = Depends(get_db),
):
    result = create_company_invite(
        db,
        company_id,
        principal.user_id,
        body.expires_hours,
    )
    write_audit(
        db,
        principal=principal,
        action="INVITE_CREATE",
        resource_type="invite",
        resource_id=result.invite.id,
        company_id=company_id,
        after={
            "company_name": result.company_name,
            "owner_name": result.owner_name,
            "expires_at": result.expires_at.isoformat(),
            "status": result.status,
        },
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(
        request,
        {
            "invite_id": result.invite.id,
            "owner_name": result.owner_name,
            "company_name": result.company_name,
            "invite_url": result.invite_url,
            "copy_text": result.copy_text,
            "expires_at": result.expires_at.isoformat(),
            "status": result.status,
            "used_at": None,
            "revoked_at": None,
        },
        "专属邀请已生成",
    )


@router.post("/invites/preview")
def preview_invite(
    body: InvitePreviewBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return ok(request, preview_company_invite(db, body.invite_token))


@router.post("/invites/confirm-start")
def confirm_invite_start(
    body: InviteConfirmStartBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    result = create_confirmation_intent(
        db,
        body.invite_token,
        body.return_url,
    )
    authorization_url = WechatOAuthClient().authorization_url(state=result.oauth_state)
    write_audit(
        db,
        principal=None,
        action="INVITE_CONFIRM_START",
        resource_type="invite_confirmation_intent",
        resource_id=result.intent_id,
        metadata={"expires_at": result.expires_at.isoformat()},
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(
        request,
        {
            "confirmation_intent": result.confirmation_intent,
            "authorization_url": authorization_url,
            "expires_at": result.expires_at.isoformat(),
        },
        "已确认，正在进入微信授权",
    )


@router.get("/invites")
def invite_records(
    request: Request,
    principal=_admin_principal(),
    db: Session = Depends(get_db),
    company_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    created_by: str | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    page_no: int = Query(default=1, alias="page", ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    items, total = list_invites(
        db,
        company_id=company_id,
        status=status,
        created_by=created_by,
        created_from=created_from,
        created_to=created_to,
        page_no=page_no,
        page_size=page_size,
    )
    return ok(request, page(items, total, page_no, page_size))


@router.get("/invites/{invite_id}")
def invite_record_detail(
    invite_id: str,
    request: Request,
    principal=_admin_principal(),
    db: Session = Depends(get_db),
):
    return ok(request, get_invite_detail(db, invite_id))


@router.post("/invites/{invite_id}/revoke")
def revoke_invite_record(
    invite_id: str,
    request: Request,
    principal=_admin_principal(),
    db: Session = Depends(get_db),
):
    invite = revoke_invite(db, invite_id)
    write_audit(
        db,
        principal=principal,
        action="INVITE_REVOKE",
        resource_type="invite",
        resource_id=invite.id,
        company_id=invite.company_id,
        after={"status": "REVOKED"},
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, {"invite_id": invite.id, "revoked": True}, "邀请已撤销")


@router.post("/invites/{invite_id}/deliveries")
def prepare_invite_channel(
    invite_id: str,
    body: InviteDeliveryBody,
    request: Request,
    principal=_admin_principal(),
    db: Session = Depends(get_db),
):
    try:
        result = prepare_invite_delivery(
            db,
            invite_id,
            body.channel,
            requested_by=principal.user_id,
            recipient=body.recipient,
        )
    except AppError as exc:
        if exc.code.startswith("INVITE_DELIVERY_"):
            write_audit(
                db,
                principal=principal,
                action="INVITE_DELIVERY_BLOCKED",
                resource_type="invite",
                resource_id=invite_id,
                metadata={"channel": body.channel, "error_code": exc.code},
                request_id=request.state.request_id,
            )
            db.commit()
        raise
    write_audit(
        db,
        principal=principal,
        action="INVITE_DELIVERY_PREPARED",
        resource_type="invite",
        resource_id=invite_id,
        metadata={"channel": result.channel, "status": result.status},
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(
        request,
        {
            "attempt_id": result.attempt_id,
            "channel": result.channel,
            "status": result.status,
            "delivered": result.delivered,
            "payload": result.payload,
            "provider_reference": result.provider_reference,
        },
    )


@router.post("/invite-matches/verified-phone")
def match_verified_phone(
    body: VerifiedPhoneMatchBody,
    request: Request,
    principal=_admin_principal(),
    db: Session = Depends(get_db),
):
    if body.verification_source == "TEST_DOUBLE" and settings.app_env.lower() == "production":
        raise AppError(
            "INVITE_PHONE_TEST_DOUBLE_DISABLED",
            "生产环境禁止使用手机号测试替身",
            403,
        )
    result = match_company_by_phone(
        db,
        body.verified_phone,
        requested_by=principal.user_id,
    )
    write_audit(
        db,
        principal=principal,
        action="INVITE_PHONE_MATCH",
        resource_type="company",
        resource_id=result["company"]["id"] if result.get("company") else None,
        metadata={
            "outcome": result["outcome"],
            "verification_source": body.verification_source,
        },
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, result)


@router.get("/invite-matches/manual")
def search_manual_match(
    request: Request,
    principal=_admin_principal(),
    db: Session = Depends(get_db),
    query: str | None = Query(default=None, max_length=128),
    region_code: str | None = Query(default=None, max_length=32),
    page_no: int = Query(default=1, alias="page", ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    items, total = manual_match_companies(
        db,
        query=query,
        region_code=region_code,
        page_no=page_no,
        page_size=page_size,
        requested_by=principal.user_id,
    )
    db.commit()
    return ok(request, page(items, total, page_no, page_size))


@router.post("/invite-matches/manual/confirm")
def confirm_manual_company_match(
    body: ManualMatchConfirmBody,
    request: Request,
    principal=_admin_principal(),
    db: Session = Depends(get_db),
):
    result = confirm_manual_match(
        db,
        body.company_id,
        requested_by=principal.user_id,
    )
    write_audit(
        db,
        principal=principal,
        action="INVITE_MANUAL_MATCH_CONFIRMED",
        resource_type="company",
        resource_id=body.company_id,
        metadata={"match_id": result["match_id"]},
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, result, "匹配对象已确认")

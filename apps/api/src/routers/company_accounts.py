from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..core.auth import Principal, require_permissions
from ..core.database import get_db
from ..core.responses import ok
from ..schemas.company_accounts import (
    CompanyAccountCreateBody,
    CompanyAccountPasswordBody,
    CompanyAccountReasonBody,
)
from ..services.audit import write_audit
from ..services.company_account_management import (
    company_account_to_dict,
    create_company_account,
    get_company_account,
    initial_password_for_company_account,
    list_company_accounts,
    require_superadmin_reason,
    reset_company_account_password,
    set_company_account_status,
)


router = APIRouter(prefix="/companies/{company_id}/accounts", tags=["company-accounts"])


def _audit_metadata(principal: Principal, reason: str | None) -> dict[str, object]:
    return {
        "operator_scope": "SUPER_ADMIN" if principal.has_any_role("SUPER_ADMIN") else "OPERATION",
        "reason_required": principal.has_any_role("SUPER_ADMIN"),
        "reason": reason,
    }


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("")
def list_company_account_endpoint(
    company_id: str,
    request: Request,
    principal: Principal = Depends(require_permissions("company.account.manage")),
    db: Session = Depends(get_db),
):
    return ok(
        request,
        [company_account_to_dict(user) for user in list_company_accounts(db, company_id)],
    )


@router.post("")
def create_company_account_endpoint(
    company_id: str,
    body: CompanyAccountCreateBody,
    request: Request,
    response: Response,
    principal: Principal = Depends(require_permissions("company.account.manage")),
    db: Session = Depends(get_db),
):
    reason = require_superadmin_reason(principal, body.reason)
    initial_password = initial_password_for_company_account(body.username, body.password)
    user = create_company_account(
        db,
        company_id=company_id,
        username=body.username,
        password=initial_password,
        display_name=body.display_name,
        role_code=body.role_code,
    )
    record = company_account_to_dict(user)
    write_audit(
        db,
        principal=principal,
        action="COMPANY_ACCOUNT_CREATE",
        resource_type="company_account",
        resource_id=user.id,
        company_id=company_id,
        before=None,
        after=record,
        metadata=_audit_metadata(principal, reason),
        request_id=request.state.request_id,
    )
    db.commit()
    _no_store(response)
    if body.password is None:
        record["initial_password"] = initial_password
    return ok(request, record, "加盟商账号已开通")


def _change_status(
    *,
    company_id: str,
    user_id: str,
    status: str,
    body: CompanyAccountReasonBody,
    request: Request,
    principal: Principal,
    db: Session,
):
    reason = require_superadmin_reason(principal, body.reason)
    user, previous_status, changed = set_company_account_status(
        db,
        company_id=company_id,
        user_id=user_id,
        status=status,
    )
    record = company_account_to_dict(user)
    if changed:
        write_audit(
            db,
            principal=principal,
            action="COMPANY_ACCOUNT_ENABLE" if status == "ACTIVE" else "COMPANY_ACCOUNT_DISABLE",
            resource_type="company_account",
            resource_id=user.id,
            company_id=company_id,
            before={"status": previous_status, "session_version": user.session_version - 1},
            after=record,
            metadata=_audit_metadata(principal, reason),
            request_id=request.state.request_id,
        )
        db.commit()
    return ok(request, record, "加盟商账号状态已更新")


@router.post("/{user_id}/enable")
def enable_company_account_endpoint(
    company_id: str,
    user_id: str,
    body: CompanyAccountReasonBody,
    request: Request,
    principal: Principal = Depends(require_permissions("company.account.manage")),
    db: Session = Depends(get_db),
):
    return _change_status(
        company_id=company_id,
        user_id=user_id,
        status="ACTIVE",
        body=body,
        request=request,
        principal=principal,
        db=db,
    )


@router.post("/{user_id}/disable")
def disable_company_account_endpoint(
    company_id: str,
    user_id: str,
    body: CompanyAccountReasonBody,
    request: Request,
    principal: Principal = Depends(require_permissions("company.account.manage")),
    db: Session = Depends(get_db),
):
    return _change_status(
        company_id=company_id,
        user_id=user_id,
        status="DISABLED",
        body=body,
        request=request,
        principal=principal,
        db=db,
    )


@router.post("/{user_id}/reset-password")
def reset_company_account_password_endpoint(
    company_id: str,
    user_id: str,
    body: CompanyAccountPasswordBody,
    request: Request,
    response: Response,
    principal: Principal = Depends(require_permissions("company.account.manage")),
    db: Session = Depends(get_db),
):
    reason = require_superadmin_reason(principal, body.reason)
    user = get_company_account(db, company_id, user_id)
    generated_password = initial_password_for_company_account(user.username or "", body.new_password)
    user, previous_session_version = reset_company_account_password(
        db,
        company_id=company_id,
        user_id=user_id,
        new_password=generated_password,
    )
    record = company_account_to_dict(user)
    write_audit(
        db,
        principal=principal,
        action="COMPANY_ACCOUNT_PASSWORD_RESET",
        resource_type="company_account",
        resource_id=user.id,
        company_id=company_id,
        before={"session_version": previous_session_version},
        after={"session_version": user.session_version},
        metadata=_audit_metadata(principal, reason),
        request_id=request.state.request_id,
    )
    db.commit()
    _no_store(response)
    record["initial_password"] = generated_password
    return ok(request, record, "加盟商账号密码已重置")

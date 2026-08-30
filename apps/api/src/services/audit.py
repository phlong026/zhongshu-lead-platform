from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from ..core.auth import Principal
from ..core.models import AuditLog

_REDACTED = "[REDACTED]"
_SENSITIVE_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "authorization",
    "cookie",
    "phone_encrypted",
    "phone_hash",
    "phone_fingerprint",
)
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
_JWT_PATTERN = re.compile(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?![A-Za-z0-9_-])")
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_COOKIE_TOKEN_PATTERN = re.compile(r"(?i)\b(?:access_token|token|session)=([^;\s,&]+)")


def _sanitize_audit_text(value: str, *, redact_phone: bool = True) -> str:
    text = _PHONE_PATTERN.sub(_REDACTED, value) if redact_phone else value
    text = _JWT_PATTERN.sub(_REDACTED, text)
    text = _BEARER_PATTERN.sub(f"Bearer {_REDACTED}", text)
    text = _COOKIE_TOKEN_PATTERN.sub(lambda match: match.group(0).split("=", 1)[0] + "=" + _REDACTED, text)
    return text


def sanitize_audit_value(value: Any, *, key: str | None = None) -> Any:
    """Recursively remove secrets and plaintext phone values before persistence.

    Key-based redaction protects structured credential fields. Value-based
    redaction additionally protects free-form note/reason/description fields in
    which users may paste phone numbers, JWTs, bearer tokens or session cookies.
    """

    normalized_key = (key or "").lower()
    if normalized_key and "masked" not in normalized_key:
        if "phone" in normalized_key or "mobile" in normalized_key:
            return _REDACTED
        if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
            return _REDACTED
    if isinstance(value, dict):
        return {
            str(item_key): sanitize_audit_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_audit_value(item) for item in value]
    if isinstance(value, str):
        identifier_key = normalized_key == "id" or normalized_key.endswith("_id")
        return _sanitize_audit_text(value, redact_phone=not identifier_key)
    return value


def write_audit(
    db: Session,
    *,
    principal: Principal | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    company_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    reason: str | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    safe_metadata = dict(metadata or {})
    if reason is not None:
        safe_metadata["reason"] = reason
    log = AuditLog(
        request_id=request_id,
        actor_user_id=principal.user_id if principal else None,
        actor_role_codes=sorted(principal.role_codes) if principal else [],
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        company_id=company_id,
        before_json=sanitize_audit_value(before) if before is not None else None,
        after_json=sanitize_audit_value(after) if after is not None else None,
        metadata_json=sanitize_audit_value(safe_metadata),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log)
    if action.startswith("V12_"):
        try:
            from .notification_v12 import project_v12_notifications

            project_v12_notifications(
                db,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                company_id=company_id,
                before=before,
                after=after,
                metadata=safe_metadata,
            )
        except Exception as exc:  # pragma: no cover - defensive projection boundary
            safe_metadata["notification_projection_error"] = type(exc).__name__
            log.metadata_json = sanitize_audit_value(safe_metadata)
    return log

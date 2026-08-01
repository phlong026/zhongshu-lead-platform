from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..core.auth import Principal
from ..core.models import AuditLog


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
    request_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    log = AuditLog(
        request_id=request_id,
        actor_user_id=principal.user_id if principal else None,
        actor_role_codes=sorted(principal.role_codes) if principal else [],
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        company_id=company_id,
        before_json=before,
        after_json=after,
        metadata_json=metadata or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log)
    return log

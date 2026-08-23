from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .errors import error_payload

settings = get_settings()

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
LEGACY_WRITE_PREFIXES = (
    "/api/v1/leads",
    "/api/v1/verification",
    "/api/v1/dispatch",
    "/api/v1/claims",
    "/api/v1/returns",
)
LEGACY_WRITE_EXACT_EXEMPTIONS = {
    "/api/v1/leads/staging-cleanup",
}
VERIFICATION_TASK_ACTIONS = {"assign", "reclaim"}


def _is_allowed_verification_task_action(path: str) -> bool:
    prefix = "/api/v1/verification/tasks/"
    if not path.startswith(prefix):
        return False
    parts = path.removeprefix(prefix).split("/")
    return len(parts) == 2 and bool(parts[0]) and parts[1] in VERIFICATION_TASK_ACTIONS


def is_legacy_write(method: str, path: str) -> bool:
    if method.upper() in SAFE_METHODS:
        return False
    if path in LEGACY_WRITE_EXACT_EXEMPTIONS or _is_allowed_verification_task_action(path):
        return False
    return any(path == prefix or path.startswith(prefix + "/") for prefix in LEGACY_WRITE_PREFIXES)


class LegacyWriteGuardMiddleware(BaseHTTPMiddleware):
    """Keep V1.0.1 history readable while preventing new legacy business facts.

    LEGACY_WRITE_ENABLED is the authoritative runtime gate. When it is false,
    legacy mutation paths fail closed regardless of APP_ENV so an environment
    label misconfiguration cannot reopen retired V1.0.1 business workflows.
    Development/tests that need historical mutation regression coverage must
    opt in explicitly with LEGACY_WRITE_ENABLED=true.
    """

    async def dispatch(self, request: Request, call_next):
        blocked = (
            not settings.legacy_write_enabled
            and is_legacy_write(request.method, request.url.path)
        )
        if blocked:
            return JSONResponse(
                status_code=410,
                content=error_payload(
                    "LEGACY_WRITE_DISABLED",
                    "V1.0.1 历史写入接口已停用，请使用 V1.2 业务接口",
                    getattr(request.state, "request_id", None),
                    {"path": request.url.path},
                ),
            )
        return await call_next(request)

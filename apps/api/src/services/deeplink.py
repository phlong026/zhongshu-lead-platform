from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt import InvalidTokenError

from ..core.config import get_settings
from ..core.errors import AppError

settings = get_settings()


def create_assignment_link_token(assignment_id: str, company_id: str, expires_hours: int = 96) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": assignment_id,
            "company_id": company_id,
            "aud": "assignment-link",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=expires_hours)).timestamp()),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_assignment_link_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience="assignment-link")
    except InvalidTokenError as exc:
        raise AppError("DEEPLINK_INVALID", "链接已失效", 400) from exc

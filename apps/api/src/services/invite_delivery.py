from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..core.invite_models import InviteDeliveryAttempt
from ..core.security import hash_phone, hash_token
from .invite_binding_service import invitation_material


class InviteDeliveryAdapter(Protocol):
    def send(
        self,
        *,
        recipient: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> str | None: ...


@dataclass(frozen=True, slots=True)
class InviteDeliveryResult:
    attempt_id: str
    channel: str
    status: str
    delivered: bool
    payload: dict[str, Any]
    provider_reference: str | None = None


_LOCAL_CHANNELS = frozenset({"COPY", "QRCODE"})
_EXTERNAL_CHANNELS = frozenset({"SMS", "WECHAT_MESSAGE"})


def _recipient_fingerprint(channel: str, recipient: str | None) -> str | None:
    if not recipient:
        return None
    if channel == "SMS":
        return hash_phone(recipient)
    return hash_token(recipient)


def prepare_invite_delivery(
    db: Session,
    invite_id: str,
    channel: str,
    *,
    requested_by: str | None,
    recipient: str | None = None,
    enabled: bool = False,
    adapter: InviteDeliveryAdapter | None = None,
    timeout_seconds: float = 10.0,
) -> InviteDeliveryResult:
    normalized = channel.strip().upper()
    if normalized not in _LOCAL_CHANNELS | _EXTERNAL_CHANNELS:
        raise AppError("INVITE_DELIVERY_CHANNEL_INVALID", "不支持的邀请发送渠道", 422)
    if not 1 <= float(timeout_seconds) <= 30:
        raise AppError("INVITE_DELIVERY_TIMEOUT_INVALID", "发送超时必须为 1 至 30 秒", 422)

    material = invitation_material(db, invite_id)
    if material.status != "ACTIVE":
        raise AppError("AUTH_INVITE_NOT_ACTIVE", "只有有效邀请可以发送", 409)
    payload = {
        "invite_id": material.invite_id,
        "company_id": material.company_id,
        "company_name": material.company_name,
        "owner_name": material.owner_name,
        "invite_url": material.invite_url,
        "copy_text": material.copy_text,
        "expires_at": material.expires_at.isoformat(),
    }
    metadata = {
        "company_id": material.company_id,
        "recipient_fingerprint": _recipient_fingerprint(normalized, recipient),
    }

    if normalized in _LOCAL_CHANNELS:
        attempt = InviteDeliveryAttempt(
            invite_id=invite_id,
            channel=normalized,
            status="PREPARED",
            delivered=False,
            requested_by=requested_by,
            metadata_json=metadata,
        )
        db.add(attempt)
        db.flush()
        return InviteDeliveryResult(
            attempt_id=attempt.id,
            channel=normalized,
            status="PREPARED",
            delivered=False,
            payload=payload,
        )

    attempt = InviteDeliveryAttempt(
        invite_id=invite_id,
        channel=normalized,
        status="PENDING",
        delivered=False,
        requested_by=requested_by,
        metadata_json=metadata,
    )
    db.add(attempt)
    db.flush()
    if not enabled or adapter is None:
        attempt.status = "DISABLED"
        attempt.error_code = "CHANNEL_DISABLED"
        db.flush()
        raise AppError(
            "INVITE_DELIVERY_CHANNEL_DISABLED",
            "该外部发送渠道尚未配置，未执行真实发送",
            409,
            {"attempt_id": attempt.id, "channel": normalized},
        )
    if not recipient:
        attempt.status = "FAILED"
        attempt.error_code = "RECIPIENT_REQUIRED"
        db.flush()
        raise AppError(
            "INVITE_DELIVERY_RECIPIENT_REQUIRED",
            "外部发送渠道必须提供接收方",
            422,
            {"attempt_id": attempt.id, "channel": normalized},
        )

    try:
        provider_reference = adapter.send(
            recipient=recipient,
            payload=payload,
            timeout_seconds=float(timeout_seconds),
        )
    except TimeoutError as exc:
        attempt.status = "FAILED"
        attempt.error_code = "DELIVERY_TIMEOUT"
        db.flush()
        raise AppError(
            "INVITE_DELIVERY_TIMEOUT",
            "邀请发送超时，不能确认已送达",
            503,
            {"attempt_id": attempt.id, "channel": normalized},
        ) from exc
    except Exception as exc:
        attempt.status = "FAILED"
        attempt.error_code = "PROVIDER_FAILURE"
        db.flush()
        raise AppError(
            "INVITE_DELIVERY_FAILED",
            "邀请发送失败，不能确认已送达",
            502,
            {"attempt_id": attempt.id, "channel": normalized},
        ) from exc

    attempt.status = "SENT"
    attempt.delivered = True
    attempt.provider_reference = provider_reference
    db.flush()
    return InviteDeliveryResult(
        attempt_id=attempt.id,
        channel=normalized,
        status="SENT",
        delivered=True,
        payload=payload,
        provider_reference=provider_reference,
    )

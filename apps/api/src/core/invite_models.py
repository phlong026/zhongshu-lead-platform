from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .models import TimestampMixin, uuid_str


class InviteBindingProfile(Base, TimestampMixin):
    """Immutable invitation target snapshot plus eventual binding trace."""

    __tablename__ = "invite_binding_profiles"

    invite_id: Mapped[str] = mapped_column(
        ForeignKey("invite_tokens.id", ondelete="CASCADE"),
        primary_key=True,
    )
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_name_snapshot: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_name_snapshot: Mapped[str | None] = mapped_column(String(64))
    token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    bound_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    bound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    target_phone_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    match_source: Mapped[str | None] = mapped_column(String(32))


class InviteConfirmationIntent(Base, TimestampMixin):
    """One-time server-verifiable proof that the user confirmed binding."""

    __tablename__ = "invite_confirmation_intents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    invite_id: Mapped[str] = mapped_column(
        ForeignKey("invite_tokens.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (
        Index(
            "ix_invite_confirmation_active_lookup",
            "invite_id",
            "purpose",
            "used_at",
            "expires_at",
        ),
    )


class InviteDeliveryAttempt(Base, TimestampMixin):
    """Delivery audit without storing invitation tokens or plaintext phones."""

    __tablename__ = "invite_delivery_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    invite_id: Mapped[str] = mapped_column(
        ForeignKey("invite_tokens.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requested_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    provider_reference: Mapped[str | None] = mapped_column(String(128))
    error_code: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class InviteMatchAttempt(Base, TimestampMixin):
    """Auditable phone/manual company match outcome with no plaintext phone."""

    __tablename__ = "invite_match_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    requested_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    phone_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    query_text: Mapped[str | None] = mapped_column(Text)
    region_code: Mapped[str | None] = mapped_column(String(32), index=True)
    selected_company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"),
        index=True,
    )
    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outcome: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

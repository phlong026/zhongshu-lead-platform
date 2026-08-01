from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def utcnow() -> datetime:
    """Return an aware UTC timestamp for all application-side time calculations."""
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    """Normalize database timestamps to aware UTC.

    PostgreSQL preserves timezone-aware values. SQLite, which is used for local
    development and automated tests, may return values from ``DateTime(timezone=True)``
    without ``tzinfo``. Normalizing at comparison boundaries keeps the business
    rules identical across both database engines.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.models import Notification, NotificationOutbox


def enqueue_outbox(
    db: Session,
    *,
    event_key: str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
) -> NotificationOutbox:
    existing = db.scalar(select(NotificationOutbox).where(NotificationOutbox.event_key == event_key))
    if existing:
        return existing
    item = NotificationOutbox(
        event_key=event_key,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        status="PENDING",
    )
    db.add(item)
    db.flush()
    return item


def create_station_message(
    db: Session,
    *,
    user_id: str | None,
    company_id: str | None,
    scene: str,
    title: str,
    body: str,
    deep_link: str | None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        company_id=company_id,
        scene=scene,
        title=title,
        body=body,
        deep_link=deep_link,
        status="CREATED",
    )
    db.add(notification)
    db.flush()
    return notification

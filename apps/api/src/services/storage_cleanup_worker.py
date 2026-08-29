from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..core.models import StorageCleanupOutbox
from ..core.security import scrub_credentials
from .storage import get_storage, storage_target_snapshot

logger = logging.getLogger("zhongshu.storage_cleanup")


def enqueue_storage_cleanup(
    db: Session,
    *,
    event_key: str,
    object_key: str,
    source_type: str,
    source_id: str,
    reason: str,
) -> StorageCleanupOutbox:
    existing = db.scalar(
        select(StorageCleanupOutbox).where(StorageCleanupOutbox.event_key == event_key)
    )
    if existing is not None:
        return existing
    backend, namespace = storage_target_snapshot()
    item = StorageCleanupOutbox(
        event_key=event_key,
        object_key=object_key,
        storage_backend=backend,
        storage_namespace=namespace,
        source_type=source_type,
        source_id=source_id,
        reason=reason,
        status="PENDING",
    )
    db.add(item)
    db.flush()
    return item


def process_storage_cleanup(db: Session, limit: int = 100) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    stmt = (
        select(StorageCleanupOutbox)
        .where(
            StorageCleanupOutbox.status.in_(["PENDING", "FAILED"]),
            or_(
                StorageCleanupOutbox.next_attempt_at.is_(None),
                StorageCleanupOutbox.next_attempt_at <= now,
            ),
        )
        .order_by(StorageCleanupOutbox.created_at, StorageCleanupOutbox.id)
        .limit(max(1, min(int(limit), 1000)))
    )
    if db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    rows = list(db.scalars(stmt).all())
    if not rows:
        return {"processed": 0, "deleted": 0, "failed": 0}
    current_backend, current_namespace = storage_target_snapshot()
    storage = None
    deleted = failed = 0
    for item in rows:
        item.status = "PROCESSING"
        item.attempts += 1
        try:
            if (
                item.storage_backend != current_backend
                or item.storage_namespace != current_namespace
            ):
                raise RuntimeError("对象存储目标已变更，请使用原存储配置处理待清理任务")
            if storage is None:
                storage = get_storage()
            storage.delete(item.object_key)
            item.status = "DELETED"
            item.deleted_at = now
            item.next_attempt_at = None
            item.last_error = None
            deleted += 1
        except Exception as exc:  # external storage boundary
            item.last_error = f"{type(exc).__name__}: {scrub_credentials(str(exc))}"
            item.status = "FAILED"
            retry_minutes = min(60, 2 ** min(item.attempts, 6))
            item.next_attempt_at = now + timedelta(minutes=retry_minutes)
            failed += 1
            log_failure = logger.error if item.attempts >= 5 else logger.warning
            log_failure(
                "storage_cleanup_failed",
                extra={
                    "cleanup_id": item.id,
                    "source_type": item.source_type,
                    "source_id": item.source_id,
                    "attempts": item.attempts,
                },
            )
    return {
        "processed": len(rows),
        "deleted": deleted,
        "failed": failed,
    }

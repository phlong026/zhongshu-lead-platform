from apps.api.src.core.models import NotificationOutbox
from apps.api.src.services.notification_service import enqueue_outbox
from apps.api.src.services.outbox_worker import process_outbox


def test_outbox_without_recipient_is_retried(db) -> None:
    item=enqueue_outbox(db,event_key="test:event",event_type="ASSIGNMENT_DISPATCHED",aggregate_type="assignment",aggregate_id="a1",payload={})
    db.commit()
    result=process_outbox(db)
    db.commit()
    assert result["failed"]==1
    assert item.status=="FAILED"
    assert item.attempts==1


def test_outbox_event_key_is_idempotent(db) -> None:
    one=enqueue_outbox(db,event_key="same:event",event_type="X",aggregate_type="x",aggregate_id="1",payload={})
    two=enqueue_outbox(db,event_key="same:event",event_type="X",aggregate_type="x",aggregate_id="1",payload={})
    assert one.id==two.id

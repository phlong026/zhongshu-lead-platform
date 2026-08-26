from pathlib import Path


def test_platform_audit_exposes_notification_failure_review_and_retry() -> None:
    source = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")

    assert "/notifications/outbox/failed" in source
    assert "/notifications/outbox/${encodeURIComponent(outboxId)}/retry" in source
    assert "notification.retry" in source
    assert "通知发送异常" in source
    assert "重新发送" in source
    assert "data-outbox-retry" in source
    assert "NOTIFICATION_RETRY:'重新发送消息'" in source
    assert "last_error" not in source
    assert 'get_by_text("通知发送异常", exact=True)' in Path("scripts/browser_smoke_v12.py").read_text(encoding="utf-8")

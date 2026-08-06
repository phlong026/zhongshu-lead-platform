from pathlib import Path


def test_h5_workbench_covers_v12_full_chain() -> None:
    html = Path("apps/h5/public/v12-workbench.html").read_text(encoding="utf-8")
    js = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")
    entry = Path("apps/h5/public/v12-workbench-entry.js").read_text(encoding="utf-8")

    assert "v12-workbench.js" in html
    for endpoint in (
        "/v1.2/reports/own",
        "/v1.2/supplier/leads",
        "/v1.2/assignments",
        "/v1.2/returns",
        "/v1.2/supplier-rewards",
        "/notifications",
    ):
        assert endpoint in js
    assert "phone_masked" in js
    assert "supplier.reward.own.read" in entry
    assert "return.own.manage" in entry


def test_admin_operations_covers_review_dispatch_return_reward_report_and_audit() -> None:
    html = Path("apps/admin/public/v12-operations.html").read_text(encoding="utf-8")
    js = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")
    entry = Path("apps/admin/public/v12-entry-link.js").read_text(encoding="utf-8")

    assert "v12-operations.js" in html
    for endpoint in (
        "/v1.2/reports/overview",
        "/v1.2/admin/supplier-leads",
        "/v1.2/dispatch-pool",
        "/v1.2/returns",
        "/v1.2/return-verifications/tasks",
        "/v1.2/supplier-rewards",
        "/v1.2/audit-events",
        "/v1.2/trace/",
    ):
        assert endpoint in js
    assert "phone_masked" in js
    assert "lead.dispatch" in entry
    assert "audit.read" in entry


def test_notification_deep_links_target_sprint5_pages() -> None:
    service = Path("apps/api/src/services/notification_v12.py").read_text(encoding="utf-8")
    worker = Path("apps/api/src/services/outbox_worker.py").read_text(encoding="utf-8")
    assert "/h5/v12-workbench.html" in service
    assert "/admin/v12-operations.html" in service
    assert 'payload.get("notification_id")' in worker

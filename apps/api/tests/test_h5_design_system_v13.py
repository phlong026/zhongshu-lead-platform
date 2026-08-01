from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
H5 = ROOT / "apps" / "h5" / "public"


def test_h5_v13_assets_are_loaded_after_base_styles():
    index = (H5 / "index.html").read_text(encoding="utf-8")
    assert "./design-system-v13.css" in index
    assert "./design-system-v13.js" in index
    assert index.index("./styles.css") < index.index("./design-system-v13.css")
    assert index.index("./design-system-v13.js") < index.index("./app.js")


def test_h5_v13_design_tokens_and_home_patch_contract():
    css = (H5 / "design-system-v13.css").read_text(encoding="utf-8")
    js = (H5 / "design-system-v13.js").read_text(encoding="utf-8")
    for token in ("--zs-brand:#7a6248", "--zs-gold:#c8a96a", "--zs-ivory:#f8f5ef"):
        assert token in css
    for selector in (".zs-v13-home", ".zs-v13-point-card", ".zs-v13-quick", ".zs-v13-lead-section"):
        assert selector in css
    assert "function zsPatchHome" in js
    assert "data-zs-route" in js
    assert "MutationObserver" in js


def test_h5_v13_lead_list_patch_contract():
    index = (H5 / "index.html").read_text(encoding="utf-8")
    css = (H5 / "lead-list-v13.css").read_text(encoding="utf-8")
    js = (H5 / "lead-list-v13.js").read_text(encoding="utf-8")
    assert "./lead-list-v13.css" in index
    assert "./lead-list-v13.js" in index
    for selector in (".zs-v13-leads-page", ".zs-v13-search", ".zs-v13-filter-row", ".zs-v13-reminder"):
        assert selector in css
    assert "function zsPatchLeadList" in js
    assert "function zsDecorateLeadCards" in js
    assert "/api/v1/dispatch/assignments" in js
    assert "data-zs-region" in js
    assert "data-zs-source" in js


def test_h5_v13_lead_detail_patch_contract():
    index = (H5 / "index.html").read_text(encoding="utf-8")
    css = (H5 / "lead-detail-v13.css").read_text(encoding="utf-8")
    js = (H5 / "lead-detail-v13.js").read_text(encoding="utf-8")
    assert "./lead-detail-v13.css" in index
    assert "./lead-detail-v13.js" in index
    for selector in (".zs-v13-detail-page", ".zs-v13-detail-card", ".zs-v13-claim-card", ".zs-v13-timeline-card"):
        assert selector in css
    assert "function zsPatchLeadDetail" in js
    assert "zs-v13-detail-route" in js
    assert "#claim-btn" in js
    assert "需求描述" in js


def test_h5_v13_points_patch_contract():
    index = (H5 / "index.html").read_text(encoding="utf-8")
    css = (H5 / "points-v13.css").read_text(encoding="utf-8")
    js = (H5 / "points-v13.js").read_text(encoding="utf-8")
    assert "./points-v13.css" in index
    assert "./points-v13.js" in index
    for selector in (".zs-v13-points-page", ".zs-v13-package-grid", ".zs-v13-ledger-list"):
        assert selector in css
    assert "function zsPatchPoints" in js
    assert "zs-v13-points-route" in js
    assert "充值档位参考" in js
    assert "积分流水" in js


def test_h5_v13_notifications_patch_contract():
    index=(H5 / "index.html").read_text(encoding="utf-8")
    css=(H5 / "notifications-v13.css").read_text(encoding="utf-8")
    js=(H5 / "notifications-v13.js").read_text(encoding="utf-8")
    assert "./notifications-v13.css" in index
    assert "./notifications-v13.js" in index
    for selector in (".zs-v13-notifications-page", ".zs-v13-notification-tabs", ".zs-v13-notification-card"):
        assert selector in css
    assert "function zsPatchNotifications" in js
    assert "function zsNotificationType" in js
    assert "/api/v1/notifications/" in js


def test_h5_v13_status_pages_contract():
    index=(H5 / "index.html").read_text(encoding="utf-8")
    css=(H5 / "status-pages-v13.css").read_text(encoding="utf-8")
    js=(H5 / "status-pages-v13.js").read_text(encoding="utf-8")
    assert "./status-pages-v13.css" in index
    assert "./status-pages-v13.js" in index
    for selector in (".zs-v13-auth-route", ".zs-v13-invite-card", ".zs-v13-state-page", ".zs-v13-link-landing"):
        assert selector in css
    assert "/auth/invites/preview" in js
    assert "window.zsRenderBindingStatus" in js
    assert "window.zsRenderReturnSuccess" in js
    assert "ZS_STATUS_NATIVE_FETCH" in js
    assert "stopImmediatePropagation" in js

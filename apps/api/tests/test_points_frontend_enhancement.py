from pathlib import Path


def test_h5_points_enhancement_exposes_low_balance_and_level_entitlements():
    script = Path("apps/h5/public/points-enhancements.js").read_text(encoding="utf-8")
    style = Path("apps/h5/public/points-enhancements.css").read_text(encoding="utf-8")
    index = Path("apps/h5/public/index.html").read_text(encoding="utf-8")
    assert "low_points_threshold" in script
    assert "level_entitlements" in script
    assert "线下充值" in script
    assert ".p1-entitlements-card" in style
    assert "points-enhancements.js" in index and "points-enhancements.css" in index


def test_admin_points_enhancement_requires_recharge_confirmation_and_supports_versioned_entitlements():
    script = Path("apps/admin/public/points-enhancements.js").read_text(encoding="utf-8")
    index = Path("apps/admin/public/index.html").read_text(encoding="utf-8")
    assert "body.confirmed = rechargeConfirmed" in script
    assert "#p-entitlements" in script
    assert "effective_at" in script and "expires_at" in script
    assert "points-enhancements.js" in index
    assert "微信支付" not in script and "支付宝支付" not in script

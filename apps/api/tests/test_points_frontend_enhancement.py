from pathlib import Path


def test_franchise_h5_points_page_is_read_only_and_business_focused() -> None:
    script = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")

    assert "/points/accounts/${encodeURIComponent(companyId)}" in script
    assert "/points/ledgers?company_id=" in script
    assert "可用积分" in script
    assert "积分流水" in script
    assert "微信支付" not in script and "支付宝支付" not in script


def test_superadmin_h5_recharge_requires_offline_collection_confirmation() -> None:
    script = Path("apps/admin/public/h5/app.js").read_text(encoding="utf-8")

    assert 'id="recharge-confirmed"' in script
    assert "我已核实本笔线下款项" in script
    assert "/points/recharge" in script
    assert "收款核验与凭证说明" in script
    assert "微信支付" not in script and "支付宝支付" not in script

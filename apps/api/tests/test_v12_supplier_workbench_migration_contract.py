from pathlib import Path


H5 = Path("apps/h5/public")


def test_supplier_lead_flow_lives_in_the_unified_franchise_workbench() -> None:
    source = (H5 / "v12-workbench.js").read_text(encoding="utf-8")

    assert "function openSupplyForm" in source
    assert "function validateSupplySubmission" in source
    assert "/v1.2/supplier/leads" in source
    assert "/revise" in source
    assert "method:'DELETE'" in source
    assert "PRE_DISPATCH_REWORK_REQUIRED" in source
    assert "id==='supply'" in source
    assert source.index("validateSupplySubmission(payload)") < source.index("api('/v1.2/supplier/leads'")


def test_unified_workbench_has_no_active_link_to_the_retired_supplier_page() -> None:
    source = (H5 / "v12-workbench.js").read_text(encoding="utf-8")

    assert "supplier.html" not in source
    assert "supplier.js" not in source
    assert "supplier.css" not in source

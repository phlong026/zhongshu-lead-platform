from pathlib import Path


def test_admin_report_enhancement_uses_role_aware_performance_endpoint():
    script = Path("apps/admin/public/report-enhancements.js").read_text(encoding="utf-8")
    style = Path("apps/admin/public/report-enhancements.css").read_text(encoding="utf-8")
    index = Path("apps/admin/public/index.html").read_text(encoding="utf-8")
    assert "/dashboard/performance?days=" in script
    assert "claim_rate" in script and "followup_rate" in script and "conversion_rate" in script
    assert "data.finance" in script
    assert ".p1-performance-report" in style
    assert "report-enhancements.js" in index and "report-enhancements.css" in index

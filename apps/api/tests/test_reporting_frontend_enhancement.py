from pathlib import Path


def test_unified_operations_home_uses_role_scoped_overview_metrics() -> None:
    script = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")

    assert "/v1.2/reports/overview" in script
    assert "ADMIN_ROLE_HOME_CONTENT" in script
    assert "roleMetricCards" in script
    assert "barChart" in script
    assert "今日运营" in script
    assert "资金风险" in script
    assert "data-overview-view" in script

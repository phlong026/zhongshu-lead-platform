from pathlib import Path


def test_unified_operations_home_uses_role_scoped_overview_metrics() -> None:
    script = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")

    assert "/v1.2/reports/overview" in script
    assert "ROLE_HOME_CONTRACT" in script
    assert "ADMIN_ROLE_HOME_CONTENT" in script
    assert "roleMetricCards" in script
    assert "运营待办" in script
    assert "资金处理" in script
    assert "?view=finance" in script

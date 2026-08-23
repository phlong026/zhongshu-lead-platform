from pathlib import Path


ADMIN = Path("apps/admin/public")


def test_admin_configuration_uses_business_language_instead_of_developer_fields() -> None:
    app = (ADMIN / "app.js").read_text(encoding="utf-8")
    points = (ADMIN / "points-enhancements.js").read_text(encoding="utf-8")
    extended = (ADMIN / "admin-extended-pages-v10.js").read_text(encoding="utf-8")

    assert "飞书暂存区" not in app
    assert "/leads/feishu/mock-sync" not in app
    assert "系统设置" in app

    for field_id in ("c-province", "c-city", "c-districts"):
        assert field_id in app
    for technical_field in (
        "field('c-code'",
        "field('c-region'",
        "field('c-category'",
        "field('r-priority'",
        "field('cfg-domain'",
        "field('cfg-key'",
        "JSON值",
    ):
        assert technical_field not in app

    assert "/companies/simple" in app
    assert "calculatePriceRulePriority" in app
    assert "等级权益（JSON）" not in points
    assert "#p-entitlements" not in points
    assert "admExtEnhancePermissions" not in extended
    assert "adm-permission-matrix" not in extended
    assert "元数据" not in extended


def test_calendar_and_roles_keep_defaults_visible_without_technical_controls() -> None:
    app = (ADMIN / "app.js").read_text(encoding="utf-8")

    assert "当前按周一至周五计算工作日，周末休息" in app
    assert "calendar-import" not in app
    assert "批量导入" not in app
    assert "roles.join('、')" not in app
    assert "权限矩阵" not in app


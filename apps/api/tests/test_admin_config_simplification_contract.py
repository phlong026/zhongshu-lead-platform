from pathlib import Path


ADMIN = Path("apps/admin/public")


def test_admin_configuration_uses_business_language_instead_of_developer_fields() -> None:
    app = (ADMIN / "app.js").read_text(encoding="utf-8")
    points = (ADMIN / "points-enhancements.js").read_text(encoding="utf-8")
    extended = (ADMIN / "admin-extended-pages-v10.js").read_text(encoding="utf-8")

    assert "飞书暂存区" not in app
    assert "暂存待处理" not in app
    assert "/leads/feishu/mock-sync" not in app
    assert "系统设置" in app

    for field_id in ("c-province", "c-city", "c-districts"):
        assert field_id in app
    assert "/master-data/region-tree" in app
    assert "PROVINCE_NAMES" not in app
    assert "全国地区数据" in app
    for technical_field in (
        "field('c-code'",
        "field('c-region'",
        "field('c-region-code'",
        "field('c-category'",
        "field('r-priority'",
        "field('cfg-domain'",
        "field('cfg-key'",
        "JSON值",
    ):
        assert technical_field not in app

    assert "/companies/simple" in app
    assert "calculatePriceRulePriority" in app
    assert "当前规则优先级" not in app
    assert "地区、类目和品牌能力维护在公司档案中" not in app
    assert "业务能力" not in app
    assert "`${x.name}（${x.code}）`" not in app
    assert "配置版本" not in app
    assert "request('/system-configs')" not in app
    assert "等级权益（JSON）" not in points
    assert "#p-entitlements" not in points
    assert "admExtEnhancePermissions" not in extended
    assert "adm-permission-matrix" not in extended
    assert "元数据" not in extended
    assert "adm-dict-sort" not in extended
    assert "adm-dict-domain" not in extended
    assert "['名称','版本','状态']" not in extended
    assert "(x.region_codes||[]).join" not in extended
    assert "ADM_LEVEL_NAMES" in extended


def test_calendar_and_roles_keep_defaults_visible_without_technical_controls() -> None:
    app = (ADMIN / "app.js").read_text(encoding="utf-8")

    assert "当前按周一至周五计算工作日，周末休息" in app
    assert "calendar-import" not in app
    assert "批量导入" not in app
    assert "calendar-source" not in app
    assert "calendar-version" not in app
    assert "roles.join('、')" not in app
    assert "权限矩阵" not in app

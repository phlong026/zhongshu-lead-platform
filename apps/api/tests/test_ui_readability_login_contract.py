from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ADMIN = ROOT / "apps" / "admin" / "public"
CALL = ROOT / "apps" / "call-h5" / "public"
H5 = ROOT / "apps" / "h5" / "public"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_user_pages_do_not_render_raw_json_or_internal_status_codes() -> None:
    admin = read(ADMIN / "app.js")
    call = read(CALL / "app.js")
    workbench = read(H5 / "v12-workbench.js")
    supplier = read(H5 / "supplier.js")

    assert "from './ui.js?v=20260823-readable-fields2'" in admin

    for raw_fragment in (
        "模板快照",
        "JSON.stringify(t.template",
        "JSON.stringify(e.payload)",
        "JSON.stringify(r,null,2)",
        "业务ID",
        "订单ID",
        "申请ID",
        "Outbox",
        "消息适配器",
        "开发模拟",
        "cm[x.company_id]||x.company_id",
        "${esc(x.type)}",
        "${esc(x.business_type)}",
        "x.source_channel||'--'",
        "x.pending_reason||''",
        "item.updated_by_name||item.updated_by",
        "roleLabels[r]||r",
        "阈值由部署环境统一管理",
        "Array.isArray(item)?item.join('、'):item",
    ):
        assert raw_fragment not in admin

    operations = read(ADMIN / "v12-operations.js")
    assert '<select class="ops-input" id="platform-lead-source">' in operations
    assert '<select class="ops-input" id="platform-lead-category">' in operations
    assert '<input\n                  class="supplier-input"\n                  id="lead-source"' not in supplier
    assert '<input\n                  class="supplier-input"\n                  id="lead-category"' not in supplier
    assert '<select class="supplier-select" id="lead-source">' in supplier
    assert '<select class="supplier-select" id="lead-category">' in supplier
    assert "'供应商推荐': '加盟商推荐'" in supplier
    assert "supplier.js?v=20260824-card-data1" in read(H5 / "supplier.html")
    assert "app.js?v=20260824-card-data1" in read(ADMIN / "index.html")
    assert "const packageDisplayName=" in admin
    assert "if(Array.isArray(value))" in read(ADMIN / "ui.js")
    for mapping in (
        "company_lead_capability:'加盟商客资能力'",
        "wechat_bind:'微信绑定'",
        "V12_COMPANY_CAPABILITY_REQUEST:'提交加盟商能力申请'",
        "WECHAT_OAUTH_START_FAILED:'微信授权未完成'",
    ):
        assert mapping in admin

    for raw_fragment in (
        "statusLabels[task.status] || task.status",
        "statusLabels[data.status] || data.status",
        "reasonLabels[request.reason_code] || request.reason_code",
        "ROLE_LABEL[role] || role",
    ):
        assert raw_fragment not in call

    for raw_fragment in (
        "LABEL[x.status]||x.status",
        "LABEL[x.lead_status]||x.lead_status",
        "LABEL[x.reason_code]||x.reason_code",
        "['派发单',x.id]",
        "['申诉编号',x.id]",
        "派发单 ${esc(x.assignment_id)}",
        "p.name||p.level_code",
        "不新增业务接口",
        "p.name||readableLabel(p.level_code,'充值档位')",
        "x.exception_reason||",
    ):
        assert raw_fragment not in workbench

    assert "const packageName=" in workbench
    assert "const rewardReason=" in workbench

    for raw_fragment in (
        "labels[status] || status",
        "labels[item.status] || item.status",
        "labels[item.review_status] || item.review_status",
    ):
        assert raw_fragment not in supplier


def test_admin_and_call_login_inputs_have_polished_accessible_structure() -> None:
    admin_js = read(ADMIN / "app.js")
    admin_css = read(ADMIN / "admin-design-system-v10.css")
    call_js = read(CALL / "app.js")
    call_css = read(CALL / "styles.css")

    for source, form_id in ((admin_js, "admin-login-form"), (call_js, "call-login-form")):
        assert f'id="{form_id}"' in source
        assert 'class="login-input-wrap"' in source
        assert 'autocomplete="username"' in source
        assert 'autocomplete="current-password"' in source
        assert 'type="password"' in source

    for source in (admin_css, call_css):
        assert ".login-input-wrap:focus-within" in source
        assert "min-height:52px" in source
        assert ".login-input-wrap input::placeholder" in source

    icon_system = read(H5 / "svg-icon-system.js")
    assert "\n    lock:" in icon_system


def test_password_login_stays_on_the_formal_role_workbench() -> None:
    admin = read(ADMIN / "app.js")
    call = read(CALL / "app.js")

    assert "location.replace('/admin/')" in admin
    assert "location.hash = '#/home'" in call
    assert "location.replace('/admin/index.html')" not in call
    assert "await boot()}catch(e)" not in admin
    assert "加盟商微信授权登录" in admin
    assert 'href="/h5/#/login"' in admin


def test_role_workbenches_return_to_the_unified_login_and_role_home() -> None:
    operations = read(ADMIN / "v12-operations.js")
    call = read(CALL / "app.js")
    workbench = read(H5 / "v12-workbench.js")

    for source in (operations, call, workbench):
        assert "/auth/logout" in source

    assert "location.replace('/admin/')" in operations
    assert "location.replace('/admin/index.html')" not in operations
    assert "location.hash = '#/home'" in call
    assert "location.replace('/h5/')" in workbench
    assert "location.replace('/admin/index.html')" not in workbench



def test_completed_returns_never_show_as_waiting_for_review() -> None:
    workbench = read(H5 / "v12-workbench.js")

    assert "const returnDecisionSummary=" in workbench
    assert "x.final_decision_reason||'待审核'" not in workbench
    assert "x?.status==='APPROVED'" in workbench
    assert "已返还" in workbench


def test_login_and_role_heroes_do_not_use_corner_decoration_blocks() -> None:
    admin_css = read(ADMIN / "admin-design-system-v10.css")
    call_css = read(CALL / "styles.css")
    legacy_h5_css = read(H5 / "styles.css")
    operations_css = read(ADMIN / "v12-operations.css")

    for source, fragments in (
        (admin_css, (".login:before", ".login:after", ".login::before", ".login::after", ".stat:after")),
        (call_css, (".login:before", ".login:after", ".login::before", ".login::after")),
        (legacy_h5_css, (".hero:after",)),
        (operations_css, (".ops-role-hero:after",)),
    ):
        for fragment in fragments:
            assert fragment not in source


def test_operation_notification_page_only_loads_superadmin_diagnostics_for_superadmin() -> None:
    admin = read(ADMIN / "app.js")

    assert "Promise.all([request('/notifications/gate0')" not in admin
    assert "can('*')?request('/notifications/gate0')" in admin
    assert "can('*')?'<button id=\"process-outbox\"" in admin


def test_company_profile_uses_business_names_instead_of_raw_codes_and_ids() -> None:
    legacy_h5 = read(H5 / "app.js")
    workbench = read(H5 / "v12-workbench.js")
    operations = read(ADMIN / "v12-operations.js")

    assert "account.level_code" not in legacy_h5
    assert "esc(state.me.company_id)" not in legacy_h5
    assert "const packageDisplayName=" in legacy_h5
    assert "app.js?v=20260824-card-data1" in read(H5 / "index.html")
    assert "const readableLabel=" in workbench
    assert "const recordCode=" in workbench
    assert "const readableLabel=" in operations
    assert "const recordCode=" in operations
    for mapping in (
        "user:'账号'",
        "followup:'跟进记录'",
        "company_lead_capability:'加盟商客资能力'",
        "wechat_bind:'微信绑定'",
    ):
        assert mapping in operations

    assert "(x.exclusion_reasons||[]).join('、')" not in operations
    assert "esc(item.company_code)" not in operations
    for mapping in (
        "COMPANY_INACTIVE:'加盟商当前未启用'",
        "RECEIVER_CAPABILITY_REQUIRED:'尚未开通接收客资能力'",
        "SELF_SUPPLY_FORBIDDEN:'不能接收自己提交的客资'",
        "SERVICE_REGION_MISMATCH:'服务区域不匹配'",
        "DUPLICATE_TO_RECEIVER:'接收方已有相同客户'",
        "POINTS_INSUFFICIENT:'可用积分不足'",
    ):
        assert mapping in operations


def test_legacy_h5_enhancements_do_not_reintroduce_codes_or_full_internal_ids() -> None:
    call = read(CALL / "app.js")
    lead_list = read(H5 / "lead-list-v13.js")
    status_pages = read(H5 / "status-pages-v13.js")
    points = read(H5 / "points-enhancements.js")
    profile = read(H5 / "profile-v13.js")
    design_system = read(H5 / "design-system-v13.js")

    assert "contactLabels[data.contact_result] || data.contact_result" not in call
    assert "conclusionLabels[data.conclusion] || data.conclusion" not in call
    assert "snapshot.category_code || '需求待核实'" not in lead_list
    assert "(x.region_codes||[]).join('、')" not in status_pages
    assert "(x.capability_codes||[]).join('、')" not in status_pages
    assert "LEAD_SUPPLIER:'供客能力'" in status_pages
    assert "LEAD_RECEIVER:'接收客资能力'" in status_pages
    assert "x.level_code||'V1'" not in status_pages
    assert "['申请编号',data.id||'已生成']" not in status_pages
    assert "深链签名" not in status_pages
    assert "account.level_code || 'V1'" not in points
    assert "档位 v${" not in points
    assert "Object.entries(account.level_entitlements || {})" not in points
    assert "const readableEntitlements" in points
    assert "points-enhancements.js?v=20260823-readable-fields2" in read(H5 / "index.html")
    assert "account.level_code||'V1'" not in profile
    assert "${level} 战略合作" not in design_system


def test_audit_resource_types_never_fall_back_to_raw_snake_case() -> None:
    admin = read(ADMIN / "app.js")
    operations = read(ADMIN / "v12-operations.js")
    ui = read(ADMIN / "ui.js")

    assert "(?:[_-][a-z0-9]+)+" in ui
    assert "(?:[_-][a-z0-9]+)+" in operations
    for mapping in (
        "company_service_area_v12:'服务区域'",
        "supplier_reward:'供客奖励'",
        "supplier_reward_batch:'奖励批次'",
        "points_package:'充值档位'",
        "lead_price_rule:'客资积分规则'",
        "points_account:'积分账户'",
        "verification_template:'电话核验内容'",
        "system_config:'规则配置'",
        "calendar_day:'工作日历'",
        "invite:'加盟邀请'",
        "rbac:'账号权限'",
        "sync_batch:'客资导入批次'",
    ):
        assert mapping in admin
        assert mapping in operations


def test_role_pages_use_franchise_business_wording_instead_of_supplier_copy() -> None:
    supplier = read(H5 / "supplier.js")
    operations = read(ADMIN / "v12-operations.js")
    workbench = read(H5 / "v12-workbench.js")
    entry = read(H5 / "v12-supplier-entry.js")
    supplier_html = read(H5 / "supplier.html")

    for phrase in (
        "供应商工作台",
        "供应商客资操作",
        "供应商客资初审",
        "供应商资料初审",
        "供应商奖励",
        "供应商客资上传",
    ):
        assert phrase not in supplier
        assert phrase not in operations
        assert phrase not in workbench
        assert phrase not in entry
        assert phrase not in supplier_html

    assert "<strong>合家美宅</strong>" in supplier
    assert "加盟商供客" in supplier
    assert "加盟商客资初审" in operations
    assert "供客奖励" in operations
    assert "供客奖励" in workbench


def test_return_evidence_ui_accepts_either_file_and_supports_inline_review() -> None:
    workbench = read(H5 / "v12-workbench.js")
    legacy = read(H5 / "app.js")
    return_v13 = read(H5 / "return-v13.js")
    operations = read(ADMIN / "v12-operations.js")

    assert "截图或录音任一类型满足即可" in workbench
    assert 'name="chat_screenshots"' in workbench
    assert 'name="call_recording"' in workbench
    assert "CHAT_SCREENSHOT" in workbench
    assert "CALL_RECORDING" in workbench
    assert "必须同时上传沟通截图和电话录音" not in workbench
    assert "截图或电话录音任一类型满足即可" in legacy
    assert "!screenshots.length&&!audio" in legacy
    assert "if(audio)" in legacy
    assert "必须同时上传沟通截图和电话录音" not in legacy
    assert "截图或电话录音任一类型满足即可" in return_v13
    assert "截图和电话录音均为必传" not in return_v13
    assert "<img" in operations
    assert "<audio controls" in operations
    assert "在线查看截图" in operations
    assert "在线播放录音" in operations


def test_unassigned_phone_verification_uses_a_clear_status_label() -> None:
    operations = read(ADMIN / "v12-operations.js")

    assert "const verificationTaskLabel=" in operations
    assert "待分配" in operations
    assert "verificationTaskBadge(x)" in operations

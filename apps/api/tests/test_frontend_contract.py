from __future__ import annotations

import re
from pathlib import Path


PUBLIC_ROOTS = [
    Path("apps/h5/public"),
    Path("apps/call-h5/public"),
    Path("apps/admin/public"),
]
PUBLIC_MOUNTS = {
    "/h5/": Path("apps/h5/public"),
    "/call/": Path("apps/call-h5/public"),
    "/admin/": Path("apps/admin/public"),
}


def _resolve_static_reference(root: Path, reference: str) -> Path:
    path = reference.split("?", 1)[0]
    for prefix, mounted_root in PUBLIC_MOUNTS.items():
        if path.startswith(prefix):
            return mounted_root / path.removeprefix(prefix)
    return root / path.lstrip("./")


def test_frontend_static_references_exist_and_are_self_contained():
    for root in PUBLIC_ROOTS:
        index = root / "index.html"
        content = index.read_text(encoding="utf-8")
        assert "https://" not in content and "http://" not in content, f"external runtime dependency in {index}"
        references = re.findall(r'(?:src|href)=["\']([^"\']+)["\']', content)
        for reference in references:
            if reference.startswith(("#", "data:", "/api/")):
                continue
            target = _resolve_static_reference(root, reference)
            assert target.exists(), f"missing static reference {reference} from {index}"
        assert (root / "logo.png").exists()


def test_frontend_api_routes_match_backend_contract():
    combined = "\n".join((root / "app.js").read_text(encoding="utf-8") for root in PUBLIC_ROOTS)
    assert "/api/v1/claim/" not in combined
    assert "`/claims/" in combined or "'/claims/" in combined
    assert "`/returns/" in combined or "'/returns/" in combined
    assert "`/followups/" in combined or "'/followups/" in combined


def test_h5_has_no_online_payment_or_native_recording_claims():
    h5 = (Path("apps/h5/public/app.js").read_text(encoding="utf-8") + Path("apps/h5/public/index.html").read_text(encoding="utf-8"))
    prohibited = ["微信支付", "支付宝支付", "自动录音", "原路退款"]
    for text in prohibited:
        assert text not in h5



def test_h5_enhancement_layer_supports_offline_and_evidence_validation():
    h5 = Path("apps/h5/public/enhancements.js").read_text(encoding="utf-8")
    css = Path("apps/h5/public/enhancements.css").read_text(encoding="utf-8")
    index = Path("apps/h5/public/index.html").read_text(encoding="utf-8")
    # P0-04：增强层不再接管微信登录跳转（唯一入口见 app.js 的 bindWechatLogin）
    assert "patchWechatLogin" not in h5 and "/auth/wechat/start" not in h5
    assert "validateEvidencePage" in h5
    assert "localStorage.setItem" in h5
    assert "h5-network-banner" in h5 and ".h5-network-banner" in css
    assert "enhancements.js" in index and "enhancements.css" in index


def test_h5_wechat_login_has_single_gated_confirm_start_entry():
    """P0-04/H3：#wechat-login 事件绑定收敛为 app.js 唯一入口，增强脚本不得覆盖。"""

    index = Path("apps/h5/public/index.html").read_text(encoding="utf-8")
    # I9：门禁范围按 index.html 实际加载的本地脚本解析，不再只扫三个硬编码
    # 文件；safe-html.js / design-system-v13.js 等同样受单一入口约束。
    loaded = []
    for reference in re.findall(r'(?:src|href)=["\']([^"\']+)["\']', index):
        if not reference.split("?", 1)[0].endswith(".js"):
            continue
        target = _resolve_static_reference(Path("apps/h5/public"), reference)
        assert target.exists(), f"missing script reference {reference}"
        loaded.append(target)
    sources = {path.name: path.read_text(encoding="utf-8") for path in loaded}
    for required in ("app.js", "enhancements.js", "status-pages-v13.js"):
        assert required in sources, f"index.html 未加载基础脚本 {required}"
    enhancement_names = tuple(name for name in sources if name != "app.js")
    # 增强脚本中任何行都不得同时出现 #wechat-login 与事件绑定（H3 可 grep 计数）
    for name in enhancement_names:
        for line in sources[name].splitlines():
            assert not ("wechat-login" in line and ("onclick" in line or "addEventListener" in line)), (
                f"{name} 恢复了对 #wechat-login 的事件绑定，违反单一入口约束"
            )
    app = sources["app.js"]
    # 唯一入口在 app.js：定义一次 + renderLogin 调用一次，内部走 confirm-start
    assert app.count("function bindWechatLogin") == 1
    assert app.count("bindWechatLogin(") == 2, "bindWechatLogin 应恰有定义与调用两处"
    # I9：onclick 计数限定在 bindWechatLogin 函数体内，登录无关的按钮赋值不再误伤。
    binder_start = app.index("function bindWechatLogin")
    binder_body = app[binder_start : app.find("\nfunction ", binder_start + 1)]
    assert binder_body.count("button.onclick") == 1, "bindWechatLogin 内应恰有一处 onclick 赋值"
    assert "/auth/invites/confirm-start" in app and "authorization_url" in app
    # I9：唯一绑定入口——confirm-start 端点只允许出现在 app.js；增强脚本即使
    # 持有 #wechat-login 引用（同意门禁对 original 的包装转发是合法形态），
    # 也无从独立发起绑定跳转，跨行赋值/变量转发不再有可利用面。
    for name in enhancement_names:
        # 剥除 // 行注释后再检：注释里说明「由 app.js 负责 confirm-start」是合法文档形态，
        # 代码形态的端点引用才构成独立绑定跳转面。
        code_only = "\n".join(line.split("//", 1)[0] for line in sources[name].splitlines())
        assert "/auth/invites/confirm-start" not in code_only, f"{name} 不得独立发起绑定跳转"
    # 门禁：邀请存在 + 规则勾选（增强层注入）+ 预览通过标记
    assert "#zs-agreement" in app and "inviteVerified" in app and "inviteInvalid" in app
    # 确认卡：预览标题 + 有效期（preview 已返回 expires_at，无新增接口）
    status_pages = sources["status-pages-v13.js"]
    assert "请确认是否绑定到" in status_pages and "邀请有效期至" in status_pages
    assert "expires_at" in status_pages
    # C2 整改：app.js 保留无邀请普通登录入口（legacy /wechat/start，不带 invite 参数），
    # 已绑定负责人重登不再被前端锁死；增强脚本仍彻底禁用旧入口。
    for name in enhancement_names:
        assert "/auth/wechat/start" not in sources[name], f"{name} 仍引用旧入口 /auth/wechat/start"
    for name, content in sources.items():
        for line in content.splitlines():
            if "/auth/wechat/start" in line:
                assert "invite=" not in line, f"{name} 不得经 wechat/start 携带 invite 参数"
    assert "/auth/wechat/start?return_url=" in app, "app.js 缺少无邀请普通登录跳转（C2）"
    # H5 不得再出现“自动绑定”文案（Phase 3 验收）
    combined = "\n".join(sources.values())
    assert "自动绑定" not in combined, "H5 登录文案不得再承诺自动绑定"


# 模块一（P0-03）供应链锁定：vendored qrcodejs 1.0.0 的哈希，
# 变更文件必须同步更新此常量并重新供应链评审（见 vendor/QR-LICENSE.txt）。
VENDORED_QRCODE_SHA256 = "c541ef06327885a8415bca8df6071e14189b4855336def4f36db54bde8484f36"
# W3C XML 命名空间常量：createElementNS/setAttributeNS 的标准参数，
# 是 qrcode.min.js 中唯一允许出现的 http 文本（死常量、无网络行为）。
_W3C_NAMESPACE_URIS = [
    "http://www.w3.org/2000/svg",
    "http://www.w3.org/2000/xmlns/",
    "http://www.w3.org/1999/xlink",
]


def test_admin_javascript_has_no_external_urls():
    """P0-03/H4：admin 下所有 js（含 vendor）不得携带任何外链。"""

    admin_root = Path("apps/admin/public")
    scripts = sorted(admin_root.rglob("*.js"))
    assert scripts, "apps/admin/public 下必须存在 js 文件"
    # I10：协议相对 URL（引号后紧跟 //host）同样构成运行时外链；注释形态的 //
    # 不紧跟引号，不受影响。
    protocol_relative = re.compile(r"""['"`]\s*//[^\s'"`]{4}""")
    for script in scripts:
        content = script.read_text(encoding="utf-8")
        # I10：W3C 命名空间死常量豁免收窄到 vendor/；第一方脚本再出现该 URI
        # 必须显式豁免评审，不再对全部 admin js 整段剥除。
        if "vendor" in script.parts:
            for uri in _W3C_NAMESPACE_URIS:
                content = content.replace(uri, "")
        assert "http://" not in content, f"external url in {script}"
        assert "https://" not in content, f"external url in {script}"
        match = protocol_relative.search(content)
        assert match is None, f"protocol-relative url in {script}: {match.group(0)!r}"
    # I10：rglob('*.js') 覆盖不到 HTML 内联脚本与 v12 独立页，按页补检。
    for page in sorted(admin_root.glob("*.html")):
        content = page.read_text(encoding="utf-8")
        assert "http://" not in content, f"external url in {page}"
        assert "https://" not in content, f"external url in {page}"
        match = protocol_relative.search(content)
        assert match is None, f"protocol-relative url in {page}: {match.group(0)!r}"


def test_admin_vendored_qrcode_is_pinned():
    """P0-03/H4：本地二维码库存在、带许可证说明且 SHA-256 与记录值一致。"""

    import hashlib

    vendor = Path("apps/admin/public/vendor/qrcode.min.js")
    assert vendor.exists(), "缺少 vendored 二维码库 vendor/qrcode.min.js"
    digest = hashlib.sha256(vendor.read_bytes()).hexdigest()
    assert digest == VENDORED_QRCODE_SHA256, "vendored qrcode.min.js 与锁定哈希不一致"
    license_note = Path("apps/admin/public/vendor/QR-LICENSE.txt").read_text(encoding="utf-8")
    for keyword in ("qrcodejs", "1.0.0", "davidshimjs", "MIT", "SHA-256", "cdnjs"):
        assert keyword in license_note, f"QR-LICENSE.txt 缺少 {keyword}"
    assert VENDORED_QRCODE_SHA256 in license_note
    index = Path("apps/admin/public/index.html").read_text(encoding="utf-8")
    assert "./vendor/qrcode.min.js" in index, "index.html 未引入本地二维码库"


def test_admin_invite_dialog_requires_confirmation_and_offers_copy_qr_revoke():
    """P0-02/P0-08/B3：邀请按钮先二次确认；弹窗含文案/复制/二维码/撤销。"""

    app = Path("apps/admin/public/app.js").read_text(encoding="utf-8")
    binding = re.search(r"querySelectorAll\('\[data-invite\]'\)\.forEach\(x=>x\.onclick=([^\n]+)", app)
    assert binding, "未找到邀请按钮的事件绑定"
    handler = binding.group(1)
    assert "inviteConfirmModal" in handler, "邀请按钮必须只打开二次确认弹窗"
    for forbidden in ("invites", "POST", "request"):
        assert forbidden not in handler, f"邀请按钮 onclick 不应直接包含 {forbidden}"
    assert "生成新的绑定邀请" in app and "原邀请将立即失效" in app, "二次确认缺少目标与失效后果文案"
    assert "copyToClipboard" in app and "navigator.clipboard" in app and "execCommand" in app, "缺少复制及其降级实现"
    assert "复制完整邀请文案" in app and "复制链接" in app, "缺少复制按钮"
    assert "copy_text" in app, "弹窗未展示后端返回的邀请文案"
    assert "renderInviteQr" in app and "new QRCode" in app and "'#invite-qr'" in app, "缺少本地二维码渲染与容器"
    assert "二维码生成失败" in app, "二维码渲染失败时缺少错误提示"
    assert "/revoke" in app and "撤销本次邀请" in app, "缺少撤销本次邀请入口"



def test_h5_auth_error_status_page_covers_binding_failures():
    app = Path("apps/h5/public/app.js").read_text(encoding="utf-8")
    assert "function renderAuthError" in app, "缺少认证错误状态页渲染函数"
    assert "auth-error" in app, "路由分发缺少 auth-error 入口"
    for code in (
        "AUTH_OAUTH_STATE_INVALID",
        "AUTH_BINDING_CONFIRM_REQUIRED",
        "AUTH_WECHAT_NOT_BOUND",
        "AUTH_WECHAT_BOUND_OTHER_COMPANY",
        "AUTH_COMPANY_DISABLED",
        "AUTH_COMPANY_ALREADY_BOUND",
        "AUTH_INVITE_INVALID",
    ):
        assert code in app, f"缺少错误码 {code} 的状态页映射"
    fn = app.split("function renderAuthError", 1)[1]
    fn = fn.split("\nfunction ", 1)[0]
    assert "e.message" not in fn and "err.message" not in fn, "状态页不得直接渲染后端 message"
    assert "重新获取" in app, "缺少重新获取邀请的引导文案"
    # P3-4：renderAuthError 注入机制统一，不得回退裸 innerHTML
    assert "innerHTML" not in fn, "renderAuthError 应统一走 zsSetSafeHtml 注入"
    # P3-5：CTA 按错误类型分化——停用类无跳转引导，已绑定类返回首页
    assert "AUTH_ACCOUNT_DISABLED" in fn and "AUTH_COMPANY_DISABLED" in fn, "停用类错误不得再共用重新获取邀请 CTA"
    assert "AUTH_COMPANY_ALREADY_BOUND" in fn and 'data-route="home"' in fn, "已绑定类错误应引导返回首页"

def test_admin_company_page_has_invite_records_modal():
    app = Path("apps/admin/public/app.js").read_text(encoding="utf-8")
    assert "data-invite-records" in app, "公司列表缺少邀请记录入口"
    assert "function inviteRecordsModal" in app, "缺少邀请记录弹窗"
    fn = app.split("function inviteRecordsModal", 1)[1]
    fn = fn.split("\nfunction ", 1)[0]
    assert "request(" in fn and "/invites" in fn, "弹窗必须请求邀请列表接口"
    assert "data-revoke" in fn, "列表行缺少撤销入口"
    assert "未记录" in app, "不可证实的追溯字段必须显示为未记录"


def test_h5_auth_error_codes_stay_in_sync_with_backend_whitelist():
    """P3-1：后端可透传错误码与 H5 文案映射双向同步，加码漏改前端在此拦截。"""

    from apps.api.src.routers.auth import _CALLBACK_SECURITY_FAILURE_CODES, _H5_AUTH_ERROR_CODES

    app = Path("apps/h5/public/app.js").read_text(encoding="utf-8")
    block = app.split("const AUTH_ERROR_META={", 1)[1].split("};", 1)[0]
    front_codes = set(re.findall(r"^ +([A-Z_]+):", block, re.M))
    assert front_codes, "未能从 app.js 解析 AUTH_ERROR_META 键集合"
    # 前端兜底键必须在；后端白名单内每个码前端都要有固定文案——否则回落
    # AUTH_FAILED 丢失特定指引（P2-1 加 WECHAT_* 码时即发生此漂移）。
    assert "AUTH_FAILED" in front_codes, "缺少 AUTH_FAILED 兜底文案"
    missing = _H5_AUTH_ERROR_CODES - front_codes
    assert not missing, f"后端透传码缺少前端文案映射: {sorted(missing)}"
    extra = front_codes - _H5_AUTH_ERROR_CODES - {"AUTH_FAILED"}
    assert not extra, f"前端文案包含后端不会下发的码（误导用户）: {sorted(extra)}"
    # 安全失败分类口径必须是可透传集合的子集，两类白名单不允许单独漂移。
    assert _CALLBACK_SECURITY_FAILURE_CODES <= _H5_AUTH_ERROR_CODES
    # 微信通道故障码的 CTA 不得是「重新获取邀请」（邀请仍有效）——它们应出现在
    # renderAuthError 的 noCta 集合中（WECHAT_SCOPE_INVALID 只往 start 端点抛，
    # 不入 callback 白名单，前端自然也不该留它的文案）。
    fn = app.split("function renderAuthError", 1)[1]
    fn = fn.split("\nfunction ", 1)[0]
    for code in (
        "WECHAT_NOT_CONFIGURED",
        "WECHAT_OAUTH_UNAVAILABLE",
        "WECHAT_OAUTH_FAILED",
    ):
        assert code in fn, f"{code} 应纳入 renderAuthError 的 CTA 分化集合"


def test_admin_invite_actions_are_permission_gated():
    """P2-2：邀请/邀请记录入口必须按 can('*') 门控——后端三个邀请接口都是
    require_permissions('*')，无 * 权限的账号（如运营）在加盟商列表页不应
    看到注定 403 的邀请入口。"""

    app = Path("apps/admin/public/app.js").read_text(encoding="utf-8")
    assert "const inviter=can('*')" in app, "companies() 必须先计算 can('*') 门控"
    # 邀请/邀请记录 span 必须整体包在 inviter 条件渲染内
    row = re.search(r"\$\{inviter\?`<td>.*?data-invite.*?data-invite-records.*?</td>`:''\}", app, re.S)
    assert row, "data-invite / data-invite-records 不得无条件渲染"
    # 操作列表头同步条件化，避免无邀请权限时出现空列
    assert re.search(r"\.\.\.\(inviter\?\['操作'\]:\[\]\)", app), "操作列必须随 inviter 门控"

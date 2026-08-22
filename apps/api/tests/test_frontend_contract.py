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

    sources = {
        name: Path("apps/h5/public", name).read_text(encoding="utf-8")
        for name in ("app.js", "enhancements.js", "status-pages-v13.js")
    }
    # 增强脚本中任何行都不得同时出现 #wechat-login 与事件绑定（H3 可 grep 计数）
    for name in ("enhancements.js", "status-pages-v13.js"):
        for line in sources[name].splitlines():
            assert not ("wechat-login" in line and ("onclick" in line or "addEventListener" in line)), (
                f"{name} 恢复了对 #wechat-login 的事件绑定，违反单一入口约束"
            )
    app = sources["app.js"]
    # 唯一入口在 app.js：定义一次 + renderLogin 调用一次，内部走 confirm-start
    assert app.count("function bindWechatLogin") == 1
    assert app.count("bindWechatLogin(") == 2, "bindWechatLogin 应恰有定义与调用两处"
    assert app.count("button.onclick") == 1, "bindWechatLogin 内应仅有一次 onclick 赋值"
    assert "/auth/invites/confirm-start" in app and "authorization_url" in app
    # 门禁：邀请存在 + 规则勾选（增强层注入）+ 预览通过标记
    assert "#zs-agreement" in app and "inviteVerified" in app and "inviteInvalid" in app
    # 确认卡：预览标题 + 有效期（preview 已返回 expires_at，无新增接口）
    status_pages = sources["status-pages-v13.js"]
    assert "请确认是否绑定到" in status_pages and "邀请有效期至" in status_pages
    assert "expires_at" in status_pages
    # 旧 OAuth 跳转入口在三脚本中彻底清零（Phase 3 步骤 6）
    for name, content in sources.items():
        assert "/auth/wechat/start" not in content, f"{name} 仍引用旧入口 /auth/wechat/start"
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
    for script in scripts:
        content = script.read_text(encoding="utf-8")
        for uri in _W3C_NAMESPACE_URIS:
            content = content.replace(uri, "")
        assert "http://" not in content, f"external url in {script}"
        assert "https://" not in content, f"external url in {script}"


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

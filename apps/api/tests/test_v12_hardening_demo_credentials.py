from __future__ import annotations

from pathlib import Path


PUBLIC_ROOTS = (
    Path("apps/admin/public"),
    Path("apps/h5/public"),
    Path("apps/call-h5/public"),
)
TEXT_SUFFIXES = {".js", ".html", ".json", ".webmanifest", ".css"}
FORBIDDEN_PUBLIC_TOKENS = (
    "Admin123!",
    "Franchise123!",
    "Telesales123!",
    "franchise_demo",
    'value="telesales"',
    "ChangeMe123!",
    "演示账号见项目文档",
    "本地演示环境",
    "进入演示",
    'id="demo-login"',
)


def _public_text_files():
    for root in PUBLIC_ROOTS:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                yield path


def test_production_frontend_static_assets_contain_no_demo_credentials() -> None:
    violations: list[str] = []
    for path in _public_text_files():
        content = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_PUBLIC_TOKENS:
            if token in content:
                violations.append(f"{path}: {token}")
    assert not violations, "production frontend exposes demo/default credentials:\n" + "\n".join(violations)


def test_admin_login_requires_credentials_and_user_creation_uses_one_time_password() -> None:
    source = Path("apps/admin/public/app.js").read_text(encoding="utf-8")
    assert 'id="admin-login-form"' in source
    assert 'id="username" name="username" type="text" autocomplete="username"' in source
    assert 'id="password" name="password" type="password" autocomplete="current-password"' in source
    assert "u-pass" not in source
    assert "initial_password" in source
    assert "初始密码仅在本次创建后显示" in source
    assert "request('/auth/login'" in source


def test_h5_login_is_wechat_only_without_demo_account_form() -> None:
    source = Path("apps/h5/public/app.js").read_text(encoding="utf-8")
    assert 'id="wechat-login"' in source
    assert "/auth/invites/confirm-start" in source
    assert 'id="username"' not in source
    assert 'id="password"' not in source
    assert "demo-login" not in source
    assert "登录方式</dt><dd>微信授权</dd>" not in source


def test_call_h5_internal_login_requires_explicit_credentials() -> None:
    source = Path("apps/call-h5/public/app.js").read_text(encoding="utf-8")
    assert 'id="call-login-form"' in source
    assert 'id="user" name="username" autocomplete="username" placeholder="请输入电销账号"' in source
    assert 'id="pass" name="password" type="password" autocomplete="current-password" placeholder="请输入登录密码"' in source
    assert 'value="telesales"' not in source
    assert "Telesales123!" not in source
    assert "api('/auth/login'" in source

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
    source = Path("apps/admin/public/v12-operations.js").read_text(encoding="utf-8")
    assert 'id="platform-login-form"' in source
    assert 'id="username" autocomplete="username" required' in source
    assert 'id="password" type="password" autocomplete="current-password" required' in source
    assert "internal-user-password" not in source[source.index("function internalUserModal") : source.index("function internalRoleModal")]
    assert "initial_password" in source
    assert "初始密码仅在当前窗口展示一次" in source
    assert "api('/auth/login'" in source


def test_franchise_h5_login_uses_explicit_credentials_without_demo_account_form() -> None:
    source = Path("apps/h5/public/v12-workbench.js").read_text(encoding="utf-8")
    assert 'id="franchise-login-form"' in source
    assert 'id="franchise-username"' in source
    assert 'id="franchise-password"' in source
    assert "demo-login" not in source
    assert "franchise_demo" not in source
    assert "api('/auth/login'" in source


def test_call_h5_internal_login_requires_explicit_credentials() -> None:
    source = Path("apps/call-h5/public/app.js").read_text(encoding="utf-8")
    assert 'id="call-login-form"' in source
    assert 'id="user" name="username" autocomplete="username" placeholder="请输入电销账号"' in source
    assert 'id="pass" name="password" type="password" autocomplete="current-password" placeholder="请输入登录密码"' in source
    assert 'value="telesales"' not in source
    assert "Telesales123!" not in source
    assert "api('/auth/login'" in source

from __future__ import annotations

from pathlib import Path


ADMIN_APP = Path("apps/admin/public/app.js")
INTERNAL_ROLES = (
    "SUPER_ADMIN",
    "OPERATION",
    "TELESALES",
)


def _source() -> str:
    return ADMIN_APP.read_text(encoding="utf-8")


def test_admin_user_page_uses_internal_role_allowlist() -> None:
    source = _source()
    assert "INTERNAL_USER_ROLES" in source
    for role in INTERNAL_ROLES:
        assert role in source

    user_section = source[source.index("async function users") : source.index("async function configs")]
    assert "FRANCHISE_OWNER" not in user_section
    assert "FRANCHISE_EMPLOYEE" not in user_section
    assert "加盟商负责人" not in user_section
    assert "内部账号" in user_section
    assert "roleChoices" in user_section
    assert 'type="radio"' in source
    assert "可多选" not in user_section


def test_admin_user_page_calls_internal_lifecycle_apis() -> None:
    source = _source()
    user_section = source[source.index("async function users") : source.index("async function configs")]

    assert "role_codes" in user_section
    assert "role_code:" not in user_section
    assert "company_id:null" not in user_section
    assert "method:'PUT'" in user_section
    assert "`/users/${id}/roles`" in user_section
    assert "`/users/${id}/disable`" in user_section
    assert "`/users/${id}/enable`" in user_section
    assert "`/users/${id}/reset-password`" in user_section
    assert "new_password" in user_section


def test_admin_user_creation_relies_on_generated_initial_password() -> None:
    source = _source()
    creation_section = source[source.index("function userModal") : source.index("function editUserRolesModal")]
    credential_section = source[
        source.index("function showCreatedUserCredentials") : source.index("function userModal")
    ]

    assert "u-pass" not in creation_section
    assert "password:" not in creation_section
    assert "initial_password" in credential_section
    assert "copy-created-user-password" in credential_section
    assert "复制账号与密码" in credential_section
    assert "if(!password)" in credential_section
    assert "账号已创建，但初始密码未返回" in credential_section
    assert "请输入姓名" in creation_section
    assert "登录账号至少输入2个字符" in creation_section
    assert "单选，仅限平台内部角色" in creation_section
    assert "8 位初始密码" in creation_section
    assert "value.trim()" in creation_section
    assert creation_section.index("showCreatedUserCredentials(created)") < creation_section.index("await users()")
    assert "账号已创建，但账号列表刷新失败" in creation_section


def test_admin_user_actions_have_busy_state_and_error_feedback() -> None:
    source = _source()
    user_section = source[source.index("async function runUserAction") : source.index("async function configs")]

    assert "runUserAction" in user_section
    assert ".disabled=true" in user_section
    assert ".disabled=false" in user_section
    assert "await users()" in user_section
    assert "completed&&(e.code==='AUTH_REQUIRED'||e.code==='AUTH_INVALID')" in user_section
    assert "请重新登录" in user_section
    assert "toast(e.message,'error')" in user_section
    assert "data-edit-user" in user_section
    assert "data-reset-user" in user_section


def test_admin_password_reset_explains_length_only_policy() -> None:
    source = _source()
    user_section = source[source.index("async function runUserAction") : source.index("async function configs")]

    assert "请输入8-128位密码，不限制字符组合" in user_section
    assert "password.length<8||password.length>128" in user_section
    assert "密码需为8-128位" in user_section
    assert "至少12位" not in user_section

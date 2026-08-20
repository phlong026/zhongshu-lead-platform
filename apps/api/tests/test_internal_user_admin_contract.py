from __future__ import annotations

from pathlib import Path


ADMIN_APP = Path("apps/admin/public/app.js")
INTERNAL_ROLES = (
    "SUPER_ADMIN",
    "OWNER",
    "LEAD_ENTRY",
    "OPERATION",
    "TELESALES",
    "FINANCE",
    "RETURN_REVIEWER",
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
    assert "加盟商负责人" not in user_section
    assert "内部账号" in user_section


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

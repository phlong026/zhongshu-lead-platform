from __future__ import annotations

import re
from pathlib import Path

from scripts.package_release import REQUIRED_RELEASE_DOCS


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOP_PATH = REPOSITORY_ROOT / "docs/runbooks/V1.2_INITIALIZATION_SOP.md"


def sop_text() -> str:
    return SOP_PATH.read_text(encoding="utf-8")


def test_initialization_sop_covers_all_roles_and_current_entries() -> None:
    content = sop_text()
    for section in (
        "管理员首装与初始化 SOP",
        "加盟商与供应商 SOP",
        "内部电销 SOP",
        "初始化验收记录",
    ):
        assert section in content

    for role_code in (
        "SUPER_ADMIN",
        "OWNER",
        "LEAD_ENTRY",
        "OPERATION",
        "TELESALES",
        "FINANCE",
        "RETURN_REVIEWER",
        "FRANCHISE_OWNER",
    ):
        assert role_code in content

    for entry in (
        "/admin/",
        "/admin/v12-operations.html",
        "/admin/index.html#/users",
        "/admin/index.html#/companies",
        "/admin/index.html#/recharge",
        "/admin/index.html#/calendar",
        "/h5/v12-workbench.html",
        "/h5/supplier.html",
        "/call/",
    ):
        assert entry in content


def test_initialization_sop_is_actionable_and_uses_current_contracts() -> None:
    content = sop_text()
    for column in ("入口", "所需角色", "操作步骤", "成功结果", "常见错误", "回退方式"):
        assert column in content

    for contract in (
        "scripts/bootstrap_superadmin.py",
        "scripts/sync_rbac.py",
        "SYSTEM_SUPERADMIN_BOOTSTRAP",
        "SYSTEM_RBAC_SYNC",
        "LAST_SUPER_ADMIN_REQUIRED",
        "AUTH_INVITE_INVALID",
        "AUTH_WECHAT_BOUND_OTHER_COMPANY",
        "LEAD_SUPPLIER",
        "LEAD_RECEIVER",
        "RETURN_VERIFY",
        "IN_PROGRESS",
        "SUBMITTED",
    ):
        assert contract in content

    assert "seed_demo.py" not in content
    assert "微信小程序" in content and "不是原生" in content


def test_initialization_sop_respects_frozen_credentials_and_configuration() -> None:
    content = sop_text()
    assert "微信 AppSecret" in content
    assert "配置参数" in content
    assert "当前暂缓" in content
    assert "不得执行" in content
    assert not re.search(
        r"(?:WECHAT_APP_SECRET|APP_SECRET|JWT_SECRET|FIELD_ENCRYPTION_KEY)\s*=",
        content,
    )
    assert "真实环境验收" in content
    assert "本地自动化" in content


def test_initialization_sop_references_existing_repository_files() -> None:
    content = sop_text()
    referenced_paths = set(
        re.findall(r"`((?:apps|scripts|docs)/[^`\s]+|Dockerfile)`", content)
    )
    assert referenced_paths
    for relative_path in sorted(referenced_paths):
        assert (REPOSITORY_ROOT / relative_path).exists(), relative_path


def test_initialization_sop_is_linked_and_required_in_release_package() -> None:
    relative_path = "docs/runbooks/V1.2_INITIALIZATION_SOP.md"
    assert relative_path in REQUIRED_RELEASE_DOCS
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    checklist = (
        REPOSITORY_ROOT / "docs/runbooks/PRODUCTION_CHECKLIST_V1.2.md"
    ).read_text(encoding="utf-8")
    assert relative_path in readme
    assert relative_path in checklist

from __future__ import annotations

from hashlib import sha256
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BRANDED_TEXT_FILES = [
    "apps/admin/public/v12-operations.html",
    "apps/admin/public/v12-operations.js",
    "apps/admin/public/h5/index.html",
    "apps/admin/public/h5/app.js",
    "apps/call-h5/public/index.html",
    "apps/h5/public/v12-workbench.html",
    "apps/h5/public/v12-workbench.js",
]
LOGO_FILES = [
    "apps/admin/public/logo.png",
    "apps/call-h5/public/logo.png",
    "apps/h5/public/logo.png",
]


def test_production_ui_uses_hejiameizhai_brand_only() -> None:
    for relative_path in BRANDED_TEXT_FILES:
        content = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        assert "合家美宅" in content, relative_path
        assert "众墅之家" not in content, relative_path


def test_production_ui_uses_one_consistent_logo_asset() -> None:
    digests = []
    for relative_path in LOGO_FILES:
        asset = REPOSITORY_ROOT / relative_path
        assert asset.is_file(), relative_path
        digests.append(sha256(asset.read_bytes()).hexdigest())
    assert len(set(digests)) == 1


def test_removed_copy_does_not_return_to_production_ui() -> None:
    all_content = "\n".join(
        (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in BRANDED_TEXT_FILES
    )
    assert "让好品牌在乡村生根" not in all_content
    assert "微信内打开 · 无需安装 · 点击即处理" not in all_content
    assert "页面、接口、数据范围和字段权限必须同时生效" not in all_content

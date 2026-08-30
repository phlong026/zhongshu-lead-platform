from __future__ import annotations

import json
import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TRACEABILITY_DOCUMENTS = (
    "docs/traceability/IMPLEMENTATION_MATRIX.md",
    "docs/traceability/V1.2_TRACEABILITY_MATRIX.md",
)
CURRENT_BRAND_DOCUMENTS = (
    "README.md",
    "docs/requirements/v1.2-prd.md",
    "docs/release/RELEASE_NOTES_V1.2.2.md",
    "docs/release/RELEASE_NOTES_V1.2.1.md",
    "docs/release/RELEASE_NOTES_V1.2.0.md",
    "docs/quality/TEST_REPORT.md",
    "docs/quality/SECURITY_AUDIT.md",
    "docs/runbooks/V1.2_PRODUCTION_EXECUTION_PLAN.md",
)


def read(relative_path: str) -> str:
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def test_rq_traceability_separates_code_automation_and_real_environment() -> None:
    matrix = read("docs/traceability/V1.2_TRACEABILITY_MATRIX.md")
    assert "代码与界面" in matrix
    assert "自动化验证" in matrix
    assert "真实环境验收" in matrix

    for number in range(1, 11):
        requirement = f"RQ-{number:03d}"
        rows = [line for line in matrix.splitlines() if f"| {requirement} " in line]
        assert len(rows) == 1, requirement
        row = rows[0]
        assert "代码存在" in row, requirement
        assert "自动化通过" in row, requirement
        assert "待真实环境验收" in row, requirement


def test_traceability_references_real_repository_paths() -> None:
    documents = "\n".join(read(path) for path in TRACEABILITY_DOCUMENTS)
    referenced_paths = set(
        re.findall(r"`((?:apps|scripts|docs)/[^`\s]+|Dockerfile)`", documents)
    )
    assert referenced_paths
    for relative_path in sorted(referenced_paths):
        assert (REPOSITORY_ROOT / relative_path).exists(), relative_path
    assert "apps/admin/public/v12-leads" not in documents
    assert "apps/admin/public/v12-operations.html" in documents

    for obsolete_path in (
        "routers/v12_leads.py",
        "services/claim_v12.py",
        "services/return_verification_v12.py",
    ):
        assert obsolete_path not in documents


def test_current_v12_delivery_documents_use_hejiameizhai_brand() -> None:
    for relative_path in CURRENT_BRAND_DOCUMENTS:
        content = read(relative_path)
        assert "合家美宅" in content, relative_path
        assert "众墅之家" not in content, relative_path

    dockerfile = read("Dockerfile")
    assert 'org.opencontainers.image.title="zhongshu-lead-platform"' in dockerfile
    assert 'org.opencontainers.image.description="合家美宅客资审核、派发与积分管理平台"' in dockerfile

    release_manifest = json.loads(read("RELEASE_MANIFEST.json"))
    assert release_manifest["product"] == "合家美宅客资审核、派发与积分管理平台"

    package_script = read("scripts/package_release.py")
    assert 'f"# 合家美宅客资平台 {version} 代码交付说明"' in package_script
    for artifact_name in (
        "完整源码.zip",
        "完整Git提交历史.bundle",
        "完整交付包.zip",
        "SHA256SUMS.txt",
    ):
        assert f"合家美宅客资平台_{{safe_version}}_{artifact_name}" in package_script
    assert 'root_name = f"zhongshu-lead-platform-{version}"' in package_script


def test_core_runbooks_identify_product_version_and_evidence_boundary() -> None:
    for relative_path in (
        "README.md",
        "docs/runbooks/DEPLOYMENT.md",
        "docs/runbooks/PRODUCTION_CHECKLIST_V1.2.md",
        "docs/runbooks/V1.2_ROLLBACK.md",
    ):
        content = read(relative_path)
        assert content.startswith("# 合家美宅客资平台 V1.2"), relative_path
        assert "代码完成" in content, relative_path
        assert "自动化通过" in content, relative_path
        assert "真实环境验收" in content, relative_path


def test_runtime_app_name_and_api_title_use_current_brand() -> None:
    config = read("apps/api/src/core/config.py")
    main = read("apps/api/src/main.py")
    assert 'app_name: str = "合家美宅客资平台"' in config
    assert 'app_version: str = "1.2.2"' in config
    assert 'title="合家美宅客资审核、派发与积分管理平台 API"' in main

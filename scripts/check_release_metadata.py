#!/usr/bin/env python3
"""Fail closed when the active release metadata drifts across files."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "1.2.2"
EXPECTED_RELEASE = f"V{EXPECTED_VERSION}"
EXPECTED_BRANCH = f"release/v{EXPECTED_VERSION}"
EXPECTED_PRODUCT = "合家美宅客资审核、派发与积分管理平台"
EXPECTED_APP_NAME = "合家美宅客资平台"


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def check_pyproject(errors: list[str]) -> None:
    pyproject = read("pyproject.toml")
    require(f'version = "{EXPECTED_VERSION}"' in pyproject, "pyproject project.version drifted", errors)
    require(f'description = "{EXPECTED_PRODUCT}"' in pyproject, "pyproject project.description drifted", errors)


def check_manifest(errors: list[str]) -> None:
    manifest = json.loads(read("RELEASE_MANIFEST.json"))
    require(manifest.get("product") == EXPECTED_PRODUCT, "RELEASE_MANIFEST product drifted", errors)
    require(manifest.get("release") == EXPECTED_RELEASE, "RELEASE_MANIFEST release drifted", errors)
    require(manifest.get("branch") == EXPECTED_BRANCH, "RELEASE_MANIFEST branch drifted", errors)
    require(manifest.get("dirty_worktree") is False, "RELEASE_MANIFEST dirty_worktree must stay false", errors)


def check_runtime_and_examples(errors: list[str]) -> None:
    config = read("apps/api/src/core/config.py")
    require(f'app_name: str = "{EXPECTED_APP_NAME}"' in config, "runtime app_name drifted", errors)
    require(f'app_version: str = "{EXPECTED_VERSION}"' in config, "runtime app_version drifted", errors)

    env_example = read(".env.example")
    docker_env = read(".env.docker.example")
    for relative_path, content in ((".env.example", env_example), (".env.docker.example", docker_env)):
        require(f"APP_NAME={EXPECTED_APP_NAME}" in content, f"{relative_path} APP_NAME drifted", errors)
        require(f"APP_VERSION={EXPECTED_VERSION}" in content, f"{relative_path} APP_VERSION drifted", errors)
    require(
        f"APP_IMAGE=registry.example.com/zhongshu-lead-platform:{EXPECTED_VERSION}@sha256:"
        in docker_env,
        ".env.docker.example APP_IMAGE tag drifted",
        errors,
    )


def check_docker_and_packaging(errors: list[str]) -> None:
    dockerfile = read("Dockerfile")
    require(f"ARG APP_VERSION={EXPECTED_VERSION}" in dockerfile, "Dockerfile APP_VERSION drifted", errors)
    require(
        f'org.opencontainers.image.description="{EXPECTED_PRODUCT}"' in dockerfile,
        "Dockerfile OCI description drifted",
        errors,
    )

    package_script = read("scripts/package_release.py")
    require(
        f'parser.add_argument("--version", default="{EXPECTED_RELEASE}")' in package_script,
        "package_release default version drifted",
        errors,
    )
    require(
        f'"docs/release/RELEASE_NOTES_{EXPECTED_RELEASE}.md"' in package_script,
        "package_release required release notes drifted",
        errors,
    )
    require(
        (ROOT / "docs" / "release" / f"RELEASE_NOTES_{EXPECTED_RELEASE}.md").is_file(),
        f"release notes missing for {EXPECTED_RELEASE}",
        errors,
    )


def check_workflows(errors: list[str]) -> None:
    pr_workflow = read(".github/workflows/v12-pr-ci.yml")
    release_workflow = read(".github/workflows/v12-release-ci.yml")
    main_workflow = read(".github/workflows/main-release.yml")
    security_workflow = read(".github/workflows/security-analysis.yml")

    require(f"- {EXPECTED_BRANCH}" in pr_workflow, "v12-pr-ci release branch drifted", errors)
    require(f"- {EXPECTED_BRANCH}" in release_workflow, "v12-release-ci release branch drifted", errors)
    require(f"--version {EXPECTED_RELEASE}-rc" in pr_workflow, "v12-pr-ci package version drifted", errors)
    require(f"--version {EXPECTED_RELEASE}" in release_workflow, "v12-release-ci package version drifted", errors)
    for name, workflow in (
        ("v12-pr-ci.yml", pr_workflow),
        ("v12-release-ci.yml", release_workflow),
        ("main-release.yml", main_workflow),
    ):
        require(
            "python scripts/check_release_metadata.py" in workflow,
            f"{name} does not call release metadata check",
            errors,
        )
    require(
        f"docker build --pull --build-arg APP_VERSION={EXPECTED_VERSION}" in security_workflow,
        "security-analysis Docker build version drifted",
        errors,
    )
    require(
        not (ROOT / ".github" / "workflows" / "v101-release.yml").exists(),
        "legacy V1.0.1 main packaging workflow must remain retired",
        errors,
    )


def check_docs(errors: list[str]) -> None:
    readme = read("README.md")
    checklist = read("docs/runbooks/PRODUCTION_CHECKLIST_V1.2.md")
    deployment = read("docs/runbooks/DEPLOYMENT.md")
    initialization = read("docs/runbooks/V1.2_INITIALIZATION_SOP.md")
    migration = read("docs/runbooks/V1.2_MIGRATION_RUNBOOK.md")
    production_plan = read("docs/runbooks/V1.2_PRODUCTION_EXECUTION_PLAN.md")
    rbac = read("docs/runbooks/V1.2_RBAC_SYNC.md")
    require(EXPECTED_BRANCH in readme, "README release branch drifted", errors)
    require(f"--version {EXPECTED_RELEASE}" in readme, "README package command drifted", errors)
    require(f"APP_VERSION={EXPECTED_VERSION}" in checklist, "production checklist APP_VERSION drifted", errors)
    require("scripts/check_binding_integrity.py" in checklist, "production checklist lacks binding integrity evidence gate", errors)
    require(EXPECTED_BRANCH in deployment, "deployment release branch drifted", errors)
    require(f":{EXPECTED_VERSION}@sha256:" in deployment, "deployment image version drifted", errors)
    require(f"release_v{EXPECTED_VERSION}" in initialization, "initialization RBAC source drifted", errors)
    require(f":{EXPECTED_VERSION}@sha256:" in migration, "migration image version drifted", errors)
    require(EXPECTED_BRANCH in production_plan, "production plan release branch drifted", errors)
    require(
        f"{EXPECTED_RELEASE} Release Candidate / Production Pending" in production_plan,
        "production plan status drifted",
        errors,
    )
    require("Release 已完成" not in production_plan, "production plan overstates release completion", errors)
    require(f"release_v{EXPECTED_VERSION}" in rbac, "RBAC runbook source drifted", errors)


def run_checks() -> list[str]:
    errors: list[str] = []
    check_pyproject(errors)
    check_manifest(errors)
    check_runtime_and_examples(errors)
    check_docker_and_packaging(errors)
    check_workflows(errors)
    check_docs(errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify active V1.2.2 release metadata consistency")
    parser.parse_args()
    errors = run_checks()
    if errors:
        for error in errors:
            print(f"release metadata error: {error}", file=sys.stderr)
        return 1
    print(f"release metadata verified: {EXPECTED_RELEASE} / {EXPECTED_BRANCH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

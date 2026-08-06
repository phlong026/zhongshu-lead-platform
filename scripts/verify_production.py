#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_production_env import derive_compose_database_url, load_dotenv, settings_for_validation
from apps.api.src.core.production import validate_production_settings


REQUIRED_FILES = (
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.prod.yml",
    "infra/nginx/production.conf.template",
    "infra/nginx/security-headers.conf",
    "docker/prepare-env.sh",
    "docker/entrypoint.sh",
    "docker/scheduler-entrypoint.sh",
    "scripts/backup_postgres.sh",
    "scripts/restore_postgres.sh",
    "scripts/baseline_v101.py",
    "scripts/migrate_v12_data.py",
    "scripts/reconcile_v12.py",
    "docs/runbooks/PRODUCTION_CHECKLIST_V1.2.md",
    "docs/runbooks/V1.2_MIGRATION_RUNBOOK.md",
    "docs/runbooks/V1.2_GO_NO_GO.md",
    "docs/runbooks/V1.2_ROLLBACK.md",
)


def image_tag(reference: str) -> str | None:
    """Return an explicit image tag without confusing a registry port for a tag."""

    without_digest = reference.split("@", 1)[0]
    last_segment = without_digest.rsplit("/", 1)[-1]
    if ":" not in last_segment:
        return None
    return last_segment.rsplit(":", 1)[1] or None


def inspect_image_version(docker: str, reference: str) -> tuple[str | None, str | None]:
    result = subprocess.run(
        [
            docker,
            "image",
            "inspect",
            reference,
            "--format",
            '{{ index .Config.Labels "org.opencontainers.image.version" }}',
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        return None, result.stderr.strip() or result.stdout.strip() or "docker image inspect failed"
    value = result.stdout.strip()
    return (value or None), None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify V1.2 production deployment prerequisites")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--require-certificates", action="store_true")
    parser.add_argument("--require-image-digest", action="store_true")
    parser.add_argument("--require-image-inspect", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    warnings: list[str] = []
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"缺少文件：{relative}")
    values = {**load_dotenv(args.env_file), **dict(os.environ)}
    if not values.get("DATABASE_URL"):
        derived = derive_compose_database_url(values)
        if derived:
            values["DATABASE_URL"] = derived
    settings = settings_for_validation(args.env_file, values)
    validation = validate_production_settings(settings, values)
    errors.extend(validation.errors)
    warnings.extend(validation.warnings)

    docker = shutil.which("docker")
    app_image = values.get("APP_IMAGE", "").strip()
    if not app_image or "example" in app_image.lower():
        errors.append("APP_IMAGE 必须指向已评审的 V1.2 镜像")
    else:
        tag = image_tag(app_image)
        if tag != settings.app_version:
            errors.append(
                f"APP_IMAGE 版本 tag 必须与 APP_VERSION 完全一致：期望 {settings.app_version}，实际 {tag or '未显式标记'}"
            )
        has_digest = "@sha256:" in app_image
        if args.require_image_digest and not has_digest:
            errors.append("正式 Go/No-Go 的 APP_IMAGE 必须使用 sha256 digest 固定")
        elif not has_digest:
            warnings.append("APP_IMAGE 尚未使用 sha256 digest 固定；正式 Go/No-Go 必须改为不可变 digest")
        if args.require_image_inspect:
            if not docker:
                errors.append("无法执行 docker image inspect，不能核验镜像 OCI 版本标签")
            else:
                image_version, inspect_error = inspect_image_version(docker, app_image)
                if inspect_error:
                    errors.append("无法检查 APP_IMAGE OCI 标签：" + inspect_error)
                elif image_version != settings.app_version:
                    errors.append(
                        f"APP_IMAGE OCI org.opencontainers.image.version 与 APP_VERSION 不一致："
                        f"期望 {settings.app_version}，实际 {image_version or '未设置'}"
                    )

    if args.require_certificates:
        for relative in ("infra/certs/fullchain.pem", "infra/certs/privkey.pem"):
            if not (ROOT / relative).is_file():
                errors.append(f"缺少 TLS 文件：{relative}")
    compose = ROOT / "docker-compose.prod.yml"
    if compose.exists():
        content = compose.read_text(encoding="utf-8")
        for marker in (
            "read_only: true",
            "no-new-privileges:true",
            "cap_drop:",
            "healthcheck:",
            "APP_IMAGE must reference the reviewed V1.2 image",
        ):
            if marker not in content:
                errors.append(f"生产 Compose 缺少安全/健康配置：{marker}")
    base_compose = ROOT / "docker-compose.yml"
    if base_compose.exists():
        content = base_compose.read_text(encoding="utf-8")
        if "DATABASE_URL: postgresql" in content:
            errors.append("docker-compose.yml 不得直接拼接未编码 DATABASE_URL，应由 docker/prepare-env.sh 安全生成")
        for marker in ("POSTGRES_USER:", "POSTGRES_PASSWORD:", "POSTGRES_DB:"):
            if marker not in content:
                errors.append(f"docker-compose.yml 缺少数据库组件配置：{marker}")
    nginx = ROOT / "infra/nginx/production.conf.template"
    if nginx.exists():
        content = nginx.read_text(encoding="utf-8")
        for marker in ("listen 443 ssl", "client_max_body_size 25m", "limit_req_zone", "X-Forwarded-Proto https"):
            if marker not in content:
                errors.append(f"生产 Nginx 缺少配置：{marker}")
    if docker and args.env_file.exists():
        command = [
            docker,
            "compose",
            "--env-file",
            str(args.env_file),
            "-f",
            str(ROOT / "docker-compose.yml"),
            "-f",
            str(compose),
            "config",
            "--quiet",
        ]
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        if result.returncode:
            errors.append("docker compose config 校验失败：" + (result.stderr.strip() or result.stdout.strip()))
    else:
        warnings.append("当前环境未执行 docker compose config；目标服务器需再次验证")
    payload = {"valid": not errors, "errors": errors, "warnings": warnings}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())

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


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify V1.2 production deployment prerequisites")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--require-certificates", action="store_true")
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
    app_image = values.get("APP_IMAGE", "").strip()
    if not app_image or "example" in app_image.lower() or "1.2." not in app_image:
        errors.append("APP_IMAGE 必须指向已评审的 V1.2 镜像")
    elif "@sha256:" not in app_image:
        warnings.append("APP_IMAGE 尚未使用 sha256 digest 固定；正式发布窗口建议改为不可变 digest")
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
    nginx = ROOT / "infra/nginx/production.conf.template"
    if nginx.exists():
        content = nginx.read_text(encoding="utf-8")
        for marker in ("listen 443 ssl", "client_max_body_size 25m", "limit_req_zone", "X-Forwarded-Proto https"):
            if marker not in content:
                errors.append(f"生产 Nginx 缺少配置：{marker}")
    docker = shutil.which("docker")
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

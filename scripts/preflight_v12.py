#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_production_env import load_dotenv

_SENSITIVE_KEY_MARKERS = ("SECRET", "PASSWORD", "TOKEN", "PRIVATE_KEY", "ACCESS_KEY")
_SENSITIVE_EXACT_KEYS = {"DATABASE_URL"}


def _sensitive_values(env: dict[str, str]) -> tuple[str, ...]:
    values: set[str] = set()
    for key, value in env.items():
        if not value:
            continue
        upper_key = key.upper()
        if upper_key in _SENSITIVE_EXACT_KEYS or any(
            marker in upper_key for marker in _SENSITIVE_KEY_MARKERS
        ):
            values.add(value)
        if upper_key == "DATABASE_URL":
            parsed = urlparse(value)
            if parsed.password:
                values.add(parsed.password)
    return tuple(sorted(values, key=len, reverse=True))


def _redact(text: str, sensitive_values: tuple[str, ...]) -> str:
    redacted = text
    for value in sensitive_values:
        redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def _database_url_from_postgres(env: dict[str, str]) -> str | None:
    """Build the same encoded internal PostgreSQL URL used by container startup."""

    user = env.get("POSTGRES_USER", "").strip()
    password = env.get("POSTGRES_PASSWORD", "").strip()
    database = env.get("POSTGRES_DB", "").strip()
    if not user or not password or not database:
        return None
    return (
        "postgresql+psycopg://"
        f"{quote(user, safe='')}:{quote(password, safe='')}@db:5432/{quote(database, safe='')}"
    )


def _compose_python_command(env_file: Path, python_args: list[str]) -> list[str]:
    docker = shutil.which("docker") or "docker"
    return [
        docker,
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(ROOT / "docker-compose.yml"),
        "-f",
        str(ROOT / "docker-compose.prod.yml"),
        "run",
        "--rm",
        "-T",
        "-e",
        "RUN_DB_MIGRATIONS=false",
        "api",
        "python",
        *python_args,
    ]


def _run(
    name: str,
    command: list[str],
    *,
    env: dict[str, str],
    sensitive_values: tuple[str, ...],
) -> dict[str, Any]:
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    except OSError as exc:
        return {
            "name": name,
            "command": command,
            "returncode": 127,
            "stdout": "",
            "stderr": _redact(str(exc), sensitive_values),
            "valid": False,
        }
    return {
        "name": name,
        "command": command,
        "returncode": result.returncode,
        "stdout": _redact(result.stdout[-12000:], sensitive_values),
        "stderr": _redact(result.stderr[-12000:], sensitive_values),
        "valid": result.returncode == 0,
    }


def _unavailable_check(name: str, command: list[str], message: str) -> dict[str, Any]:
    return {
        "name": name,
        "command": command,
        "returncode": 127,
        "stdout": "",
        "stderr": message,
        "valid": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="V1.2 production Go/No-Go preflight")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--require-certificates", action="store_true")
    parser.add_argument("--allow-incomplete-backfill", action="store_true")
    parser.add_argument(
        "--compose-database",
        action="store_true",
        help="Run Alembic/reconciliation inside the production Compose network and require immutable image verification",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "v12-preflight.json")
    args = parser.parse_args()

    env_file = args.env_file.resolve()
    values = load_dotenv(env_file)
    env = {**values, **os.environ}
    explicit_database_url = bool(env.get("DATABASE_URL", "").strip())
    if args.compose_database and not explicit_database_url:
        derived = _database_url_from_postgres(env)
        if derived:
            env["DATABASE_URL"] = derived
    sensitive_values = _sensitive_values(env)
    python = sys.executable

    verify_args = [
        python,
        "scripts/verify_production.py",
        "--env-file",
        str(env_file),
        *(["--require-certificates"] if args.require_certificates else []),
        *(["--require-image-digest", "--require-image-inspect"] if args.compose_database else []),
    ]
    commands: list[tuple[str, list[str]]] = [
        (
            "production-environment",
            [python, "scripts/validate_production_env.py", "--env-file", str(env_file)],
        ),
        ("deployment-prerequisites", verify_args),
    ]
    database_revision = ["-m", "alembic", "-c", "alembic.ini", "current", "--check-heads"]
    reconciliation = [
        "scripts/reconcile_v12.py",
        *(["--allow-incomplete-backfill"] if args.allow_incomplete_backfill else []),
    ]

    checks = [_run(name, command, env=env, sensitive_values=sensitive_values) for name, command in commands]
    if args.compose_database:
        if not shutil.which("docker"):
            checks.extend(
                [
                    _unavailable_check(
                        "database-revision",
                        ["docker", "compose", "<unavailable>"],
                        "docker CLI 不可用，无法在 Compose 网络内验证生产数据库",
                    ),
                    _unavailable_check(
                        "v12-reconciliation",
                        ["docker", "compose", "<unavailable>"],
                        "docker CLI 不可用，无法在 Compose 网络内验证生产数据库",
                    ),
                ]
            )
        else:
            checks.extend(
                [
                    _run(
                        "database-revision",
                        _compose_python_command(env_file, database_revision),
                        env=env,
                        sensitive_values=sensitive_values,
                    ),
                    _run(
                        "v12-reconciliation",
                        _compose_python_command(env_file, reconciliation),
                        env=env,
                        sensitive_values=sensitive_values,
                    ),
                ]
            )
    elif explicit_database_url:
        checks.extend(
            [
                _run(
                    "database-revision",
                    [python, *database_revision],
                    env=env,
                    sensitive_values=sensitive_values,
                ),
                _run(
                    "v12-reconciliation",
                    [python, *reconciliation],
                    env=env,
                    sensitive_values=sensitive_values,
                ),
            ]
        )
    else:
        message = "未显式配置 DATABASE_URL；Docker 生产部署必须使用 --compose-database，禁止回退到本地 SQLite"
        checks.extend(
            [
                _unavailable_check("database-revision", [python, *database_revision], message),
                _unavailable_check("v12-reconciliation", [python, *reconciliation], message),
            ]
        )

    payload = {
        "valid": all(item["valid"] for item in checks),
        "env_file": str(env_file),
        "compose_database": bool(args.compose_database),
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

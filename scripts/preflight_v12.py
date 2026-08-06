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
    """Build the same internal PostgreSQL URL used by docker-compose.yml.

    The URL is used by host-side configuration validation only. Database reads
    are executed inside the Compose network so the `db` hostname is reachable.
    """

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


def main() -> int:
    parser = argparse.ArgumentParser(description="V1.2 production Go/No-Go preflight")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--require-certificates", action="store_true")
    parser.add_argument("--allow-incomplete-backfill", action="store_true")
    parser.add_argument(
        "--compose-database",
        action="store_true",
        help="Run Alembic/reconciliation inside the production Compose network",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "v12-preflight.json")
    args = parser.parse_args()

    env_file = args.env_file.resolve()
    values = load_dotenv(env_file)
    # Runtime-injected variables have the same precedence used by Settings and
    # validate_production_env.py, so the report reflects the process that will run.
    env = {**values, **os.environ}
    if args.compose_database and not env.get("DATABASE_URL"):
        derived = _database_url_from_postgres(env)
        if derived:
            env["DATABASE_URL"] = derived
    sensitive_values = _sensitive_values(env)
    python = sys.executable

    commands: list[tuple[str, list[str]]] = [
        (
            "production-environment",
            [python, "scripts/validate_production_env.py", "--env-file", str(env_file)],
        ),
        (
            "deployment-prerequisites",
            [
                python,
                "scripts/verify_production.py",
                "--env-file",
                str(env_file),
                *(["--require-certificates"] if args.require_certificates else []),
            ],
        ),
    ]
    database_revision = ["-m", "alembic", "-c", "alembic.ini", "current", "--check-heads"]
    reconciliation = [
        "scripts/reconcile_v12.py",
        *(["--allow-incomplete-backfill"] if args.allow_incomplete_backfill else []),
    ]
    if args.compose_database:
        if not shutil.which("docker"):
            commands.extend(
                [
                    ("database-revision", ["docker", "compose", "<unavailable>"]),
                    ("v12-reconciliation", ["docker", "compose", "<unavailable>"]),
                ]
            )
        else:
            commands.extend(
                [
                    ("database-revision", _compose_python_command(env_file, database_revision)),
                    ("v12-reconciliation", _compose_python_command(env_file, reconciliation)),
                ]
            )
    else:
        commands.extend(
            [
                ("database-revision", [python, *database_revision]),
                ("v12-reconciliation", [python, *reconciliation]),
            ]
        )

    checks: list[dict[str, Any]] = []
    for name, command in commands:
        if command[-1:] == ["<unavailable>"]:
            checks.append(
                {
                    "name": name,
                    "command": command,
                    "returncode": 127,
                    "stdout": "",
                    "stderr": "docker CLI 不可用，无法在 Compose 网络内验证生产数据库",
                    "valid": False,
                }
            )
            continue
        checks.append(_run(name, command, env=env, sensitive_values=sensitive_values))

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

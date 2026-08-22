from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
TARGET_TESTS = (
    "apps/api/tests/test_v12_production_lifecycle_e2e.py",
    "apps/api/tests/test_internal_user_postgres_concurrency_e2e.py",
    "apps/api/tests/test_invite_binding_postgres_concurrency_e2e.py",
)
SAFE_DATABASE_MARKERS = ("e2e", "test", "ci")
SAFE_ENVIRONMENT_KEYS = (
    "CI",
    "GITHUB_ACTIONS",
    "LANG",
    "LC_ALL",
    "PATH",
    "PYTHONPATH",
    "PYTHONPYCACHEPREFIX",
    "SYSTEMROOT",
    "TMP",
    "TMPDIR",
    "TEMP",
    "UV_CACHE_DIR",
    "VIRTUAL_ENV",
)


class DisposablePostgres:
    def __init__(self) -> None:
        suffix = uuid4().hex[:10]
        self.name = f"zs-v12-e2e-{suffix}"
        self.password = f"zs-v12-e2e-{uuid4().hex}"
        self.database = "zhongshu_e2e"
        self.user = "zhongshu"
        self.port: str | None = None

    @property
    def database_url(self) -> str:
        if not self.port:
            raise RuntimeError("临时 PostgreSQL 端口尚未解析")
        return (
            f"postgresql+psycopg://{self.user}:{self.password}"
            f"@127.0.0.1:{self.port}/{self.database}"
        )

    def start(self) -> None:
        _run_checked(["docker", "--version"])
        _run_checked(["docker", "info"])
        _run_checked(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                self.name,
                "-e",
                f"POSTGRES_DB={self.database}",
                "-e",
                f"POSTGRES_USER={self.user}",
                "-e",
                f"POSTGRES_PASSWORD={self.password}",
                "-p",
                "127.0.0.1::5432",
                "postgres:16-alpine",
            ]
        )
        self.port = _read_container_port(self.name)
        self._wait_until_ready()

    def stop(self) -> None:
        _run(["docker", "stop", self.name], check=False, capture_output=True)

    def _wait_until_ready(self) -> None:
        last_error = ""
        for _attempt in range(60):
            result = _run(
                [
                    "docker",
                    "exec",
                    self.name,
                    "pg_isready",
                    "-U",
                    self.user,
                    "-d",
                    self.database,
                ],
                check=False,
                capture_output=True,
            )
            if result.returncode == 0:
                return
            last_error = (result.stderr or result.stdout or "").strip()
            time.sleep(1)
        raise RuntimeError(f"临时 PostgreSQL 未就绪: {last_error}")


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, **kwargs)


def _run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return _run(command, capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        message = f"命令失败: {' '.join(command)}"
        if detail:
            message = f"{message}\n{detail}"
        raise RuntimeError(message) from exc


def _read_container_port(container_name: str) -> str:
    result = _run_checked(["docker", "port", container_name, "5432/tcp"])
    endpoint = result.stdout.strip().splitlines()[0]
    return endpoint.rsplit(":", 1)[-1]


def _validate_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if not parsed.scheme.lower().startswith("postgresql"):
        raise ValueError("V12 E2E 只允许使用 PostgreSQL 隔离数据库")
    database = (parsed.path or "").rsplit("/", 1)[-1].lower()
    if not database or not any(marker in database for marker in SAFE_DATABASE_MARKERS):
        raise ValueError("V12 E2E 数据库名必须包含 e2e/test/ci，避免误连生产库")
    return database_url


def _isolated_test_environment() -> dict[str, str]:
    return {
        key: os.environ[key]
        for key in SAFE_ENVIRONMENT_KEYS
        if os.environ.get(key)
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run V1.2 production lifecycle E2E")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("V12_E2E_DATABASE_URL", "").strip(),
        help=(
            "Empty isolated PostgreSQL URL. Database name must contain e2e/test/ci; "
            "existing data makes the lifecycle test fail by design."
        ),
    )
    parser.add_argument(
        "--evidence-path",
        default="dist/e2e/v12-production-lifecycle-evidence.json",
        help="Path for JSON evidence written by the lifecycle test.",
    )
    parser.add_argument(
        "--junit-xml",
        default="dist/e2e/v12-production-lifecycle.xml",
        help="Path for pytest JUnit XML output.",
    )
    return parser


def _run_lifecycle(database_url: str, evidence_path: str, junit_xml: str) -> int:
    evidence = ROOT / evidence_path
    junit = ROOT / junit_xml
    evidence.parent.mkdir(parents=True, exist_ok=True)
    junit.parent.mkdir(parents=True, exist_ok=True)
    evidence.unlink(missing_ok=True)
    junit.unlink(missing_ok=True)
    env = _isolated_test_environment()
    env.update(
        {
            "APP_ENV": "test",
            "TRUSTED_HOSTS": "testserver,app.example.com",
            "V12_E2E_DATABASE_URL": _validate_database_url(database_url),
            "V12_E2E_EVIDENCE_PATH": str(evidence),
        }
    )
    result = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            *TARGET_TESTS,
            "--junitxml",
            str(junit),
        ],
        env=env,
    )
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    database_url = args.database_url
    postgres: DisposablePostgres | None = None
    try:
        if not database_url:
            postgres = DisposablePostgres()
            postgres.start()
            database_url = postgres.database_url
        return _run_lifecycle(database_url, args.evidence_path, args.junit_xml)
    finally:
        if postgres is not None:
            postgres.stop()


def _cli() -> int:
    try:
        return main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_cli())

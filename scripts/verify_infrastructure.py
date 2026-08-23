#!/usr/bin/env python3
"""Verify V1.2 production P1 infrastructure readiness on the target host.

Checks the reference 4C8G Tencent Cloud topology required by Issue #42:
host spec, Docker/Compose, PostgreSQL 16 network exposure and persistent
data volume, NTP/clock sync, public listeners, TLS certificates, private
object storage hardening and dev/staging/production isolation.

The script is host-side, secret-free and writes a desensitized JSON evidence
record. Sensitive environment values are redacted from any captured output.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

_SENSITIVE_KEY_MARKERS = ("SECRET", "PASSWORD", "TOKEN", "PRIVATE_KEY", "ACCESS_KEY", "CREDENTIAL")
_SENSITIVE_EXACT_KEYS = {"DATABASE_URL"}


def sensitive_values(env: dict[str, str]) -> tuple[str, ...]:
    values: set[str] = set()
    for key, value in env.items():
        if not value:
            continue
        upper_key = key.upper()
        if upper_key in _SENSITIVE_EXACT_KEYS or any(
            marker in upper_key for marker in _SENSITIVE_KEY_MARKERS
        ):
            values.add(value)
    return tuple(sorted(values, key=len, reverse=True))


def redact(text: str, values: tuple[str, ...]) -> str:
    redacted = text
    for value in values:
        redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def parse_meminfo(text: str) -> int | None:
    match = re.search(r"^MemTotal:\s+(\d+)\s+kB", text, re.MULTILINE)
    return int(match.group(1)) // 1024 if match else None


def parse_ss_listeners(text: str) -> list[dict[str, str]]:
    listeners: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.strip().startswith("LISTEN"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_address = parts[3]
        port = local_address.rsplit(":", 1)[-1]
        address = local_address.rsplit(":", 1)[0]
        listeners.append({"address": address, "port": port, "line": line.strip()})
    return listeners


def is_public_bind(address: str) -> bool:
    return address in {"0.0.0.0", "*", "::", "[::]"} or (
        address not in {"127.0.0.1", "::1"} and not address.startswith("127.")
    )


def is_tencent_cos_endpoint(endpoint_url: str) -> bool:
    hostname = urlparse(endpoint_url).hostname
    return bool(hostname and hostname.endswith(".myqcloud.com"))


def parse_timedatectl(text: str) -> dict[str, str]:
    """Parse both `timedatectl show` (KEY=value) and status (KEY: value) formats."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        for separator in ("=", ":"):
            if separator in line:
                key, _, value = line.partition(separator)
                result[key.strip()] = value.strip()
                break
    return result


def days_until_expiry(openssl_output: str) -> int | None:
    match = re.search(r"notAfter=([A-Za-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{4}\s+GMT)", openssl_output)
    if not match:
        return None
    try:
        expiry = datetime.strptime(match.group(1), "%b %d %H:%M:%S %Y GMT").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    remaining = expiry - datetime.now(timezone.utc)
    if remaining.total_seconds() < 0:
        return 0
    return remaining.days if remaining == timedelta(days=remaining.days) else remaining.days + 1


def check_env_isolation(env: dict[str, str], environment: str) -> list[str]:
    errors: list[str] = []
    if environment != "production":
        return errors
    non_prod_markers = ("staging", "-dev", "dev.", "localhost", "example.com", "127.0.0.1")
    for key in ("APP_DOMAIN", "APP_BASE_URL", "CORS_ORIGINS", "TRUSTED_HOSTS", "S3_BUCKET", "POSTGRES_DB"):
        value = env.get(key, "").strip()
        if not value:
            errors.append(f"{key} 未配置，无法确认 production 环境隔离")
            continue
        lowered = value.lower()
        if any(marker in lowered for marker in non_prod_markers):
            errors.append(f"{key} 含有非 production 标识（当前值含 dev/staging/local/example 标记）")
    return errors


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def run_capture(
    command: list[str], *, sensitive: tuple[str, ...], timeout: int = 30
) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            command, text=True, capture_output=True, timeout=timeout, errors="replace"
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", redact(str(exc), sensitive)
    return proc.returncode, redact(proc.stdout, sensitive), redact(proc.stderr, sensitive)


def which(tool: str) -> str | None:
    return shutil.which(tool)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--environment", default="production", choices=("production", "staging", "dev"))
    parser.add_argument("--expected-public-ports", default="80,443", help="comma separated public ports")
    parser.add_argument("--require-tls", action="store_true", help="fail when TLS certificate files are missing")
    parser.add_argument("--require-object-storage", action="store_true", help="fail when object storage hardening is unverifiable")
    parser.add_argument("--postgres-data-bind", default="", help="host path the production postgres data volume is bound to")
    parser.add_argument("--output", type=Path, help="JSON evidence output path")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    env = load_dotenv(args.env_file)
    env.update(dict(os.environ))
    sensitive = sensitive_values(env)
    evidence: dict[str, object] = {}
    errors: list[str] = []
    warnings: list[str] = []

    # Host spec (reference: 4C8G)
    cpu = os.cpu_count() or 0
    mem_mb: int | None = None
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace")
        mem_mb = parse_meminfo(meminfo)
    except OSError:
        warnings.append("无法读取 /proc/meminfo（非 Linux 或权限受限）")
    evidence["host_spec"] = {
        "cpu_cores": cpu,
        "memory_mb": mem_mb,
        "os_release": _read_release(),
    }
    if cpu < 4:
        errors.append(f"CPU 核数不足参考规格：{cpu} < 4")
    if mem_mb is not None and mem_mb < 8 * 1024:
        errors.append(f"内存不足参考规格：{mem_mb}MB < 8192MB")

    # Docker / Compose
    docker = which("docker")
    docker_server: str | None = None
    compose_version: str | None = None
    if docker:
        code, out, err = run_capture([docker, "info", "--format", "{{.ServerVersion}}"], sensitive=sensitive)
        if code == 0 and out.strip():
            docker_server = out.strip()
        else:
            warnings.append(f"Docker daemon 不可达：{err.strip() or out.strip() or 'unknown'}")
        code, out, _ = run_capture([docker, "compose", "version"], sensitive=sensitive)
        if code == 0:
            compose_version = out.strip()
    else:
        errors.append("未安装 Docker CLI")
    evidence["docker"] = {"cli": docker, "server_version": docker_server, "compose": compose_version}
    if not docker_server:
        errors.append("Docker daemon 未运行")
    if not compose_version:
        errors.append("Docker Compose 插件不可用")

    # PostgreSQL 16 exposure + persistent volume
    pg = _check_postgres(docker, sensitive, errors, warnings, args)
    evidence["postgresql"] = pg

    # NTP + container clock
    ntp = _check_ntp(docker, sensitive, warnings)
    evidence["ntp"] = ntp

    # Public listeners
    listeners = _check_listeners(args.expected_public_ports, sensitive, errors, warnings)
    evidence["listeners"] = listeners

    # TLS
    tls = _check_tls(args.require_tls, sensitive, errors, warnings)
    evidence["tls"] = tls

    # Object storage
    storage = _check_object_storage(env, args.require_object_storage, sensitive, errors, warnings)
    evidence["object_storage"] = storage

    # Environment isolation
    isolation = {"errors": check_env_isolation(env, args.environment)}
    errors.extend(isolation["errors"])
    evidence["environment_isolation"] = isolation

    evidence.update(
        {
            "environment": args.environment,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "hostname": os.uname().nodename if hasattr(os, "uname") else None,
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
        }
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.quiet or errors:
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


def _read_release() -> str | None:
    for path in ("/etc/os-release", "/etc/redhat-release"):
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace").strip().splitlines()[0]
        except OSError:
            continue
    return None


def _check_postgres(
    docker: str | None,
    sensitive: tuple[str, ...],
    errors: list[str],
    warnings: list[str],
    args: argparse.Namespace,
) -> dict[str, object]:
    result: dict[str, object] = {"image": None, "container": None, "version": None, "published_ports": []}
    if not docker:
        errors.append("缺少 Docker，无法验证 PostgreSQL 16")
        return result
    code, out, err = run_capture(
        [docker, "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Ports}}"], sensitive=sensitive
    )
    rows = [line.split("\t") for line in out.splitlines() if "\t" in line] if code == 0 else []
    db_rows = [row for row in rows if row[1].startswith("postgres:16")]
    if not db_rows:
        code, out, _ = run_capture([docker, "images", "--format", "{{.Repository}}:{{.Tag}}"], sensitive=sensitive)
        has_image = any(line == "postgres:16-alpine" for line in out.splitlines()) if code == 0 else False
        if has_image:
            warnings.append("已存在 postgres:16-alpine 镜像，但未发现运行中的 db 容器")
        else:
            errors.append("未发现 PostgreSQL 16 容器或镜像")
        return result
    name, image, ports = db_rows[0]
    result["image"] = image
    result["container"] = name
    result["version"] = "16"
    result["published_ports"] = [p.strip() for p in ports.split(",") if p.strip()]
    for entry in result["published_ports"]:
        if ":5432->" in entry and not entry.startswith("127.0.0.1:") and not entry.startswith("[::1]:"):
            errors.append(f"PostgreSQL 5432 被发布到非回环地址：{entry}")
    if args.postgres_data_bind:
        bind = Path(args.postgres_data_bind)
        if not bind.is_dir():
            errors.append(f"PostgreSQL 数据卷宿主目录不存在：{args.postgres_data_bind}")
        else:
            result["data_bind"] = str(bind)
            result["data_bind_fs"] = _fs_of(bind)
    else:
        volume = _postgres_data_volume(docker, name, sensitive)
        if volume:
            result["data_volume"] = volume
            code, out, _ = run_capture(
                [docker, "volume", "inspect", volume, "--format", "{{.Mountpoint}}"], sensitive=sensitive
            )
            if code == 0 and out.strip():
                result["data_volume_mountpoint"] = out.strip().splitlines()[0]
    return result


def _postgres_data_volume(docker: str, container: str, sensitive: tuple[str, ...]) -> str | None:
    code, out, _ = run_capture(
        [docker, "inspect", container, "--format", "{{range .Mounts}}{{.Name}}|{{.Destination}}\\n{{end}}"],
        sensitive=sensitive,
    )
    if code != 0:
        return None
    for line in out.splitlines():
        if "|/var/lib/postgresql/data" in line:
            name = line.split("|", 1)[0].strip()
            if name:
                return name
    return None


def _fs_of(path: Path) -> dict[str, str] | None:
    if not shutil.which("df"):
        return None
    try:
        proc = subprocess.run(
            ["df", "-T", "--output=source,fstype,size,avail", str(path)],
            text=True, capture_output=True, timeout=15, errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode:
        return None
    lines = proc.stdout.splitlines()
    if len(lines) < 2:
        return None
    cols = lines[1].split()
    if len(cols) < 4:
        return None
    return {"source": cols[0], "fstype": cols[1], "size": cols[2], "avail": cols[3]}


def _check_ntp(docker: str | None, sensitive: tuple[str, ...], warnings: list[str]) -> dict[str, object]:
    result: dict[str, object] = {"synchronized": None, "detail": None, "clock_offset_seconds": None}
    if shutil.which("timedatectl"):
        code, out, _ = run_capture(["timedatectl", "show"], sensitive=sensitive)
        if code == 0:
            parsed = parse_timedatectl(out)
            ntp = parsed.get("NTPSynchronized")
            result["synchronized"] = ntp == "yes" if ntp else None
            result["detail"] = {k: parsed.get(k) for k in ("NTPSynchronized", "TimeUSec", "LocalRTC") if k in parsed}
    if result["synchronized"] is None and shutil.which("chronyc"):
        code, out, _ = run_capture(["chronyc", "tracking"], sensitive=sensitive)
        if code == 0:
            result["synchronized"] = "Leap status" in out and "Normal" in out
            result["detail"] = out.strip()
    if result["synchronized"] is None:
        warnings.append("无法读取 NTP 同步状态（timedatectl/chronyc 均不可用）")
    if docker:
        code, out, _ = run_capture(
            [docker, "ps", "--format", "{{.Names}}\t{{.Image}}"], sensitive=sensitive
        )
        db_row = next(
            (line.split("\t")[0] for line in out.splitlines() if "\t" in line and "postgres:16" in line.split("\t")[1]),
            None,
        )
        if db_row:
            code, out, _ = run_capture([docker, "exec", db_row, "date", "-u", "+%s"], sensitive=sensitive)
            if code == 0 and out.strip().isdigit():
                host_code, host_out, _ = run_capture(["date", "-u", "+%s"], sensitive=sensitive)
                if host_code == 0 and host_out.strip().isdigit():
                    result["clock_offset_seconds"] = abs(int(out.strip()) - int(host_out.strip()))
    return result


def _check_listeners(
    expected_public_ports: str,
    sensitive: tuple[str, ...],
    errors: list[str],
    warnings: list[str],
) -> dict[str, object]:
    expected = {port.strip() for port in expected_public_ports.split(",") if port.strip()}
    result: dict[str, object] = {"expected_public_ports": sorted(expected), "public_listeners": []}
    if not shutil.which("ss"):
        warnings.append("缺少 ss，无法检查监听端口")
        return result
    code, out, _ = run_capture(["ss", "-tlnp"], sensitive=sensitive)
    if code:
        warnings.append("ss -tlnp 执行失败")
        return result
    listeners = parse_ss_listeners(out)
    public = [entry for entry in listeners if is_public_bind(entry["address"])]
    result["public_listeners"] = public
    unexpected = [entry for entry in public if entry["port"] not in expected]
    for entry in unexpected:
        errors.append(f"公网监听端口不在放行清单：{entry['address']}:{entry['port']}")
    return result


def _check_tls(
    require_tls: bool, sensitive: tuple[str, ...], errors: list[str], warnings: list[str]
) -> dict[str, object]:
    cert = ROOT / "infra" / "certs" / "fullchain.pem"
    key = ROOT / "infra" / "certs" / "privkey.pem"
    result: dict[str, object] = {"fullchain_present": cert.is_file(), "privkey_present": key.is_file(), "expires_in_days": None}
    if cert.is_file() and key.is_file():
        if shutil.which("openssl"):
            code, out, _ = run_capture(
                ["openssl", "x509", "-in", str(cert), "-noout", "-enddate"], sensitive=sensitive
            )
            if code == 0:
                result["expires_in_days"] = days_until_expiry(out)
                if result["expires_in_days"] is not None and result["expires_in_days"] < 30:
                    errors.append(f"TLS 证书将在 {result['expires_in_days']} 天内到期")
        else:
            warnings.append("缺少 openssl，无法校验证书到期时间")
    elif require_tls:
        errors.append("缺少 TLS 证书文件（infra/certs/fullchain.pem 与 privkey.pem）")
    else:
        warnings.append("TLS 证书未配置（P1 验收需 --require-tls 通过）")
    return result


def _check_object_storage(
    env: dict[str, str],
    require_storage: bool,
    sensitive: tuple[str, ...],
    errors: list[str],
    warnings: list[str],
) -> dict[str, object]:
    result: dict[str, object] = {
        "backend": env.get("OBJECT_STORAGE_BACKEND", "").strip() or "s3",
        "bucket": env.get("S3_BUCKET", "").strip(),
        "endpoint": env.get("S3_ENDPOINT_URL", "").strip(),
        "region": env.get("S3_REGION", "").strip(),
    }
    has_creds = bool(env.get("S3_ACCESS_KEY_ID") and env.get("S3_SECRET_ACCESS_KEY"))
    result["credentials_configured"] = has_creds
    if not has_creds or not result["bucket"]:
        if require_storage:
            errors.append("对象存储凭据/Bucket 未配置，无法验证加密/版本/生命周期/审计")
        else:
            warnings.append("对象存储凭据未配置（P1 验收需 --require-object-storage 通过）")
        return result
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        warnings.append("缺少 boto3，无法验证对象存储配置")
        return result
    session = boto3.session.Session(
        aws_access_key_id=env["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=env["S3_SECRET_ACCESS_KEY"],
        region_name=env.get("S3_REGION", "") or None,
    )
    endpoint_url = env.get("S3_ENDPOINT_URL") or None
    client_options: dict[str, object] = {"endpoint_url": endpoint_url}
    if is_tencent_cos_endpoint(endpoint_url or ""):
        client_options["config"] = Config(s3={"addressing_style": "virtual"})
    client = session.client("s3", **client_options)
    checks: dict[str, object] = {}
    for name, method in (
        ("encryption", "get_bucket_encryption"),
        ("versioning", "get_bucket_versioning"),
        ("lifecycle", "get_bucket_lifecycle_configuration"),
        ("public_access_block", "get_public_access_block"),
        ("logging", "get_bucket_logging"),
    ):
        try:
            getattr(client, method)(Bucket=result["bucket"])
            checks[name] = "configured"
        except ClientError as exc:
            checks[name] = f"not-configured: {redact(str(exc), sensitive)}"
        except BotoCoreError as exc:
            checks[name] = f"error: {redact(str(exc), sensitive)}"
    result["hardening"] = checks
    for name in ("encryption", "versioning", "lifecycle"):
        if checks.get(name) != "configured":
            errors.append(f"对象存储 {name} 未配置/无法验证")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

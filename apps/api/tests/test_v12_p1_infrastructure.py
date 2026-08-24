from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.verify_infrastructure import (
    _execute_validated_command,
    _validated_command,
    check_env_isolation,
    days_until_expiry,
    is_public_bind,
    is_tencent_cos_endpoint,
    load_dotenv,
    parse_meminfo,
    parse_ss_listeners,
    parse_timedatectl,
    redact,
    sensitive_values,
)


def test_parse_meminfo_returns_mib() -> None:
    text = "MemTotal:       16384000 kB\nMemFree:        8000000 kB\n"
    assert parse_meminfo(text) == 16000


def test_parse_meminfo_missing_is_none() -> None:
    assert parse_meminfo("MemFree: 1 kB\n") is None


def test_parse_ss_listeners_extracts_address_and_port() -> None:
    text = (
        "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        "LISTEN 0 4096 127.0.0.1:55440 0.0.0.0:* users:((\"postgres\",pid=1,fd=3))\n"
        "LISTEN 0 511 0.0.0.0:80 0.0.0.0:* users:((\"nginx\",pid=9,fd=6))\n"
    )
    listeners = parse_ss_listeners(text)
    assert [(entry["address"], entry["port"]) for entry in listeners] == [
        ("127.0.0.1", "55440"),
        ("0.0.0.0", "80"),
    ]


def test_is_public_bind_classifies_wildcard_and_loopback() -> None:
    assert is_public_bind("0.0.0.0") is True
    assert is_public_bind("::") is True
    assert is_public_bind("10.0.0.5") is True
    assert is_public_bind("127.0.0.1") is False
    assert is_public_bind("::1") is False


def test_is_tencent_cos_endpoint_only_matches_myqcloud_hosts() -> None:
    assert is_tencent_cos_endpoint("https://cos.ap-shanghai.myqcloud.com") is True
    assert is_tencent_cos_endpoint("https://s3.example.com") is False
    assert is_tencent_cos_endpoint("") is False


def test_parse_timedatectl_extracts_sync_state() -> None:
    text = "NTPSynchronized=yes\nTimeUSec=Wed 2026-08-12 10:00:00 CST\nLocalRTC=no\n"
    parsed = parse_timedatectl(text)
    assert parsed["NTPSynchronized"] == "yes"
    assert parsed["LocalRTC"] == "no"


def test_days_until_expiry_computes_positive_remaining() -> None:
    expiry = (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%b %d %H:%M:%S %Y GMT")
    assert days_until_expiry(f"notAfter={expiry}") == 90


def test_days_until_expiry_rejects_garbage() -> None:
    assert days_until_expiry("notAfter=not-a-date") is None


def test_sensitive_values_collects_secret_like_keys() -> None:
    env = {
        "JWT_SECRET": "jwt-value",
        "POSTGRES_PASSWORD": "db-pass",
        "S3_SECRET_ACCESS_KEY": "s3-secret",
        "APP_DOMAIN": "app.example.com",
        "DATABASE_URL": "postgresql://u:url-pass@db:5432/d",
    }
    values = sensitive_values(env)
    assert "jwt-value" in values
    assert "db-pass" in values
    assert "s3-secret" in values
    assert "app.example.com" not in values


def test_redact_replaces_all_sensitive_values() -> None:
    text = "db-pass and jwt-value and db-pass again"
    assert redact(text, ("db-pass", "jwt-value")) == "[REDACTED] and [REDACTED] and [REDACTED] again"


def test_infrastructure_command_allowlist_rejects_shells() -> None:
    with pytest.raises(ValueError, match="不允许"):
        _validated_command(["sh", "-c", "id"])


def test_infrastructure_command_allowlist_rejects_invalid_docker_resource_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.verify_infrastructure.shutil.which",
        lambda name: "/usr/bin/docker" if name == "docker" else None,
    )

    with pytest.raises(ValueError, match="资源名"):
        _validated_command(
            ["/usr/bin/docker", "exec", "db;touch-pwned", "date", "-u", "+%s"]
        )


def test_infrastructure_command_allowlist_accepts_fixed_docker_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.verify_infrastructure.shutil.which",
        lambda name: "/usr/bin/docker" if name == "docker" else None,
    )
    command = ["/usr/bin/docker", "ps", "--format", "{{.Names}}\t{{.Image}}"]

    assert _validated_command(command) == command


def test_infrastructure_executes_docker_probe_with_resolved_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command: list[str], **kwargs: object) -> Result:
        seen["command"] = command
        seen["executable"] = kwargs.get("executable")
        return Result()

    monkeypatch.setattr("scripts.verify_infrastructure.subprocess.run", fake_run)
    command = ["/usr/bin/docker", "ps", "--format", "{{.Names}}\t{{.Image}}"]

    _execute_validated_command(command, timeout=30)

    assert seen["command"] == ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"]
    assert seen["executable"] == "/usr/bin/docker"


def test_check_env_isolation_rejects_non_production_markers() -> None:
    env = {
        "APP_DOMAIN": "app.staging.example.com",
        "APP_BASE_URL": "https://localhost:8080",
        "CORS_ORIGINS": "https://app.example.com",
        "TRUSTED_HOSTS": "app.example.com",
        "S3_BUCKET": "zhongshu-dev",
        "POSTGRES_DB": "zhongshu",
    }
    errors = check_env_isolation(env, "production")
    assert any("APP_DOMAIN" in error for error in errors)
    assert any("APP_BASE_URL" in error for error in errors)
    assert any("S3_BUCKET" in error for error in errors)


def test_check_env_isolation_accepts_clean_production_values() -> None:
    env = {
        "APP_DOMAIN": "app.zhongshu.example",
        "APP_BASE_URL": "https://app.zhongshu.example",
        "CORS_ORIGINS": "https://app.zhongshu.example",
        "TRUSTED_HOSTS": "app.zhongshu.example",
        "S3_BUCKET": "zhongshu-private",
        "POSTGRES_DB": "zhongshu",
    }
    assert check_env_isolation(env, "production") == []


def test_check_env_isolation_skips_non_production() -> None:
    env = {"APP_DOMAIN": "localhost", "S3_BUCKET": "zhongshu-dev"}
    assert check_env_isolation(env, "staging") == []


def test_load_dotenv_parses_quoted_and_unquoted(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=production\nAPP_DOMAIN=\"app.example.com\"\nS3_BUCKET='zhongshu-private'\n", encoding="utf-8"
    )
    values = load_dotenv(Path(env_file))
    assert values["APP_ENV"] == "production"
    assert values["APP_DOMAIN"] == "app.example.com"
    assert values["S3_BUCKET"] == "zhongshu-private"

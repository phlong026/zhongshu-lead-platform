from __future__ import annotations

from pathlib import Path

from scripts import secret_scan


def test_secret_scan_flags_real_config_secrets_and_allows_placeholders() -> None:
    safe_text = """
JWT_SECRET=replace-with-jwt-secret
FIELD_ENCRYPTION_KEY=change-me-in-production
PHONE_HASH_SECRET=dev-phone-hash-secret
PHONE_FINGERPRINT_SECRET=ci-phone-fingerprint-secret-at-least-32-characters
WECHAT_APP_SECRET=your-wechat-app-secret
FEISHU_APP_SECRET=
S3_SECRET_ACCESS_KEY=<腾讯云 CAM SecretKey>
"""
    assert secret_scan.find_secret_hits(Path(".env.example"), safe_text) == []

    leaked_values = {
        key: f"prod-{key.lower()}-" + "x" * 24
        for key in secret_scan.SECRET_KEYS
    }
    leaked_text = "\n".join(f"{key}={value}" for key, value in leaked_values.items())
    hits = secret_scan.find_secret_hits(Path("deploy.env"), leaked_text)
    assert {hit.key for hit in hits} == secret_scan.SECRET_KEYS

    quoted = secret_scan.find_secret_hits(
        Path("settings.json"),
        '"jwt_secret": "prod-secret-value-abcdefghijklmnopqrstuvwxyz"',
    )
    assert [hit.key for hit in quoted] == ["JWT_SECRET"]

    yaml = secret_scan.find_secret_hits(
        Path("settings.yml"),
        "WECHAT_APP_SECRET: prod-secret-value-abcdefghijklmnopqrstuvwxyz",
    )
    assert [hit.key for hit in yaml] == ["WECHAT_APP_SECRET"]

    annotation = secret_scan.find_secret_hits(
        Path("config.py"),
        'jwt_secret: str = "dev-change-me-at-least-32-characters-long"',
    )
    assert annotation == []


def test_secret_scan_only_uses_git_tracked_files() -> None:
    script = Path("scripts/secret_scan.py").read_text(encoding="utf-8")
    assert "git" in script and "ls-files" in script
    assert ".rglob(" not in script


def test_current_tracked_repository_has_no_detected_secret() -> None:
    assert secret_scan.scan_tracked_files() == []

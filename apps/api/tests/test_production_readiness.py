from __future__ import annotations

from pathlib import Path

from apps.api.src.core.config import Settings
from apps.api.src.core.production import validate_production_settings


def _secret(prefix: str, length: int = 40) -> str:
    return prefix + ("x" * max(0, length - len(prefix)))


def production_settings(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "app_version": "1.2.1",
        "app_base_url": "https://app.zhongshu.example.cn",
        "database_url": "postgresql+psycopg://zhongshu:secret@db:5432/zhongshu",
        "jwt_secret": "J" * 48,
        "field_encryption_key": "E" * 48,
        "phone_hash_secret": "H" * 32,
        "phone_fingerprint_secret": "F" * 48,
        "wechat_app_id": "wx-production",
        "wechat_app_secret": _secret("wechat"),
        "wechat_oauth_redirect_uri": "https://app.zhongshu.example.cn/api/v1/auth/wechat/callback",
        "wechat_dev_mock": False,
        "feishu_enabled": True,
        "feishu_app_id": "cli-production",
        "feishu_app_secret": _secret("feishu"),
        "feishu_app_token": "test-bitable-token",
        "feishu_table_id": "table-id",
        "feishu_dev_mock": False,
        "object_storage_backend": "local",
        "cors_origins": "https://app.zhongshu.example.cn",
        "trusted_hosts": "app.zhongshu.example.cn",
        "auto_create_schema": False,
        "legacy_write_enabled": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _production_env(**overrides: str) -> dict[str, str]:
    values = {
        "POSTGRES_PASSWORD": "test-strong-production-password-2026",
        "SEED_DEMO": "false",
        "TRUSTED_PROXY_CIDR": "127.0.0.1/32",
        "TRUST_PROXY_HEADERS": "true",
    }
    values.update(overrides)
    return values


def test_production_validation_accepts_strong_configuration_with_local_storage_warning():
    result = validate_production_settings(production_settings(), _production_env())
    assert result.valid is True
    assert not result.errors
    assert any("本地对象存储" in warning for warning in result.warnings)


def test_production_validation_accepts_aws_s3_default_endpoint():
    result = validate_production_settings(
        production_settings(
            object_storage_backend="s3",
            s3_endpoint_url="",
            s3_access_key_id="aws-access-key",
            s3_secret_access_key=_secret("aws"),
            s3_bucket="zhongshu-private",
            s3_region="ap-southeast-1",
        ),
        _production_env(),
    )
    assert result.valid is True
    assert not any("S3_ENDPOINT_URL" in error for error in result.errors)


def test_production_validation_accepts_tencent_cos_shanghai():
    result = validate_production_settings(
        production_settings(
            object_storage_backend="s3",
            s3_endpoint_url="https://cos.ap-shanghai.myqcloud.com",
            s3_access_key_id="cos-secret-id",
            s3_secret_access_key=_secret("cos"),
            s3_bucket="hejiameizhai-private-1250000000",
            s3_region="ap-shanghai",
        ),
        _production_env(),
    )
    assert result.valid is True
    assert not result.errors


def test_production_validation_rejects_cos_bucket_without_appid():
    result = validate_production_settings(
        production_settings(
            object_storage_backend="s3",
            s3_endpoint_url="https://cos.ap-shanghai.myqcloud.com",
            s3_access_key_id="cos-secret-id",
            s3_secret_access_key=_secret("cos"),
            s3_bucket="hejiameizhai-private",
            s3_region="ap-shanghai",
        ),
        _production_env(),
    )
    assert result.valid is False
    assert any("BucketName-APPID" in error for error in result.errors)


def test_production_validation_rejects_cos_endpoint_region_mismatch():
    result = validate_production_settings(
        production_settings(
            object_storage_backend="s3",
            s3_endpoint_url="https://cos.ap-guangzhou.myqcloud.com",
            s3_access_key_id="cos-secret-id",
            s3_secret_access_key=_secret("cos"),
            s3_bucket="hejiameizhai-private-1250000000",
            s3_region="ap-shanghai",
        ),
        _production_env(),
    )
    assert result.valid is False
    assert any("S3_REGION" in error for error in result.errors)


def test_production_validation_rejects_insecure_custom_s3_endpoint():
    result = validate_production_settings(
        production_settings(
            object_storage_backend="s3",
            s3_endpoint_url="http://cos.internal.example.com",
            s3_access_key_id="cos-access-key",
            s3_secret_access_key=_secret("cos"),
            s3_bucket="zhongshu-private",
            s3_region="ap-guangzhou",
        ),
        _production_env(),
    )
    assert result.valid is False
    assert any("S3_ENDPOINT_URL" in error for error in result.errors)


def test_production_validation_allows_explicitly_disabled_feishu_without_credentials():
    result = validate_production_settings(
        production_settings(
            feishu_enabled=False,
            feishu_app_id="",
            feishu_app_secret="",
            feishu_app_token="",
            feishu_table_id="",
        ),
        _production_env(),
    )
    assert result.valid is True
    assert not any("FEISHU_" in error for error in result.errors)


def test_production_validation_requires_feishu_credentials_when_enabled():
    result = validate_production_settings(
        production_settings(feishu_app_token="", feishu_table_id=""),
        _production_env(),
    )
    assert result.valid is False
    assert any("FEISHU_APP_TOKEN" in error for error in result.errors)
    assert any("FEISHU_TABLE_ID" in error for error in result.errors)


def test_production_validation_rejects_shared_phone_secrets():
    result = validate_production_settings(
        production_settings(phone_hash_secret="S" * 40, phone_fingerprint_secret="S" * 40),
        _production_env(),
    )
    assert result.valid is False
    assert any("必须与 PHONE_HASH_SECRET 独立" in error for error in result.errors)


def test_production_validation_rejects_legacy_write_enablement():
    result = validate_production_settings(
        production_settings(legacy_write_enabled=True),
        _production_env(),
    )
    assert result.valid is False
    assert any("LEGACY_WRITE_ENABLED=false" in error for error in result.errors)


def test_production_validation_rejects_untrusted_or_malformed_proxy_cidr():
    bad_values = (
        "*",
        "0.0.0.0/0",
        "::/0",
        "",
        "not-a-cidr",
        "127.0.0.1",
        "127.0.0.1/32; set_real_ip_from 0.0.0.0/0",
        "127.0.0.1/32 trailing",
        "127.0.0.2/24",
    )
    for value in bad_values:
        result = validate_production_settings(
            production_settings(),
            _production_env(TRUSTED_PROXY_CIDR=value),
        )
        assert result.valid is False, value
        assert any("TRUSTED_PROXY_CIDR" in error for error in result.errors), value


def test_production_validation_requires_explicit_trust_proxy_headers():
    """M-B：nginx 生产拓扑会强制覆写 x-real-ip，忘设/误设开关会让审计 IP 全部
    失真为反代内网地址且静默失败——必须显式设置为 true 才放行。"""

    for bad in ("", "false", "yes", "1"):
        overrides = {"TRUST_PROXY_HEADERS": bad}
        result = validate_production_settings(production_settings(), _production_env(**overrides))
        assert result.valid is False, repr(bad)
        assert any("TRUST_PROXY_HEADERS" in error for error in result.errors), repr(bad)


def test_production_validation_accepts_single_canonical_proxy_cidr():
    for value in ("127.0.0.1/32", "10.20.30.0/24", "2001:db8::/64"):
        result = validate_production_settings(
            production_settings(),
            _production_env(TRUSTED_PROXY_CIDR=value),
        )
        assert result.valid is True, (value, result.errors)


def test_production_validation_rejects_placeholders_mocks_and_insecure_urls():
    result = validate_production_settings(
        production_settings(
            app_version="1.0.1",
            app_base_url="http://localhost:8000",
            database_url="sqlite:///./prod.db",
            jwt_secret="dev-" + "change-me",
            field_encryption_key="replace-key",
            phone_hash_secret="dev-secret",
            phone_fingerprint_secret="",
            wechat_dev_mock=True,
            feishu_dev_mock=True,
            cors_origins="*",
            trusted_hosts="*",
            legacy_write_enabled=True,
        ),
        {
            "POSTGRES_PASSWORD": "change-this-database-password",
            "SEED_DEMO": "true",
            "TRUSTED_PROXY_CIDR": "0.0.0.0/0",
        },
    )
    assert result.valid is False
    assert len(result.errors) >= 10


def test_production_deployment_files_enforce_tls_least_privilege_and_fail_closed_restore():
    compose = Path("docker-compose.prod.yml").read_text(encoding="utf-8")
    nginx = Path("infra/nginx/production.conf.template").read_text(encoding="utf-8")
    headers = Path("infra/nginx/security-headers.conf").read_text(encoding="utf-8")
    entrypoint = Path("docker/entrypoint.sh").read_text(encoding="utf-8")
    restore = Path("scripts/restore_postgres.sh").read_text(encoding="utf-8")
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose and "AUTO_CREATE_SCHEMA" in compose
    assert 'LEGACY_WRITE_ENABLED: "false"' in compose
    assert "TRUSTED_PROXY_CIDR" in compose
    # M-B：生产拓扑 nginx 强制覆写 x-real-ip，api 服务必须固定注入信任开关，
    # 否则审计 IP 恒为反代内网地址（静默失真）。
    assert 'TRUST_PROXY_HEADERS: "true"' in compose
    assert "listen 443 ssl" in nginx and "return 301 https://" in nginx
    assert "client_max_body_size 25m" in nginx and "limit_req_zone" in nginx
    assert "set_real_ip_from ${TRUSTED_PROXY_CIDR};" in nginx
    assert "Strict-Transport-Security" in headers and "Content-Security-Policy" in headers
    assert "validate_production_env.py" in entrypoint
    assert "CONFIRM_RESTORE" in restore and "sha256sum -c" in restore
    assert "--exit-on-error" in restore and "ON_ERROR_STOP=1" in restore
    assert "RESTORE_SUCCEEDED=false" in restore
    assert "RESTORE_RESTART_SERVICES:-NO" in restore
    assert 'if [ "$RESTORE_SUCCEEDED" = "true" ] && [ "$RESTART" = "YES" ]' in restore
    assert "compose stop api scheduler lead-export-worker" in restore
    assert "compose up -d api scheduler lead-export-worker" in restore
    assert (
        "restore did not complete successfully; api, scheduler and "
        "lead-export-worker remain stopped"
    ) in restore
    assert (
        "restore completed; api, scheduler and lead-export-worker remain stopped"
        in restore
    )


def test_health_and_api_responses_include_version_security_and_no_store(api_client):
    client, _ = api_client
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["version"] == client.app.version
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"
    unauthorized = client.get("/api/v1/auth/me")
    assert unauthorized.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in unauthorized.headers["content-security-policy"]
    assert unauthorized.headers["x-content-type-options"] == "nosniff"

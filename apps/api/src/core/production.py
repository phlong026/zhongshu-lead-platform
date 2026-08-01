from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from .config import Settings


_PLACEHOLDER_MARKERS = ("replace-", "change-this", "dev-", "example", "changeme")


@dataclass(frozen=True)
class ProductionValidation:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors


def _unsafe_secret(value: str, *, minimum: int) -> bool:
    lowered = value.lower()
    return len(value) < minimum or any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def validate_production_settings(settings: Settings, environ: dict[str, str] | None = None) -> ProductionValidation:
    env = environ or dict(os.environ)
    errors: list[str] = []
    warnings: list[str] = []
    if settings.app_env.lower() != "production":
        errors.append("APP_ENV 必须设置为 production")
    parsed = urlparse(settings.app_base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append("APP_BASE_URL 必须使用有效 HTTPS 域名")
    if not settings.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        errors.append("生产环境 DATABASE_URL 必须使用 PostgreSQL")
    for name, value, minimum in (
        ("JWT_SECRET", settings.jwt_secret, 32),
        ("FIELD_ENCRYPTION_KEY", settings.field_encryption_key, 32),
        ("PHONE_HASH_SECRET", settings.phone_hash_secret, 24),
    ):
        if _unsafe_secret(value, minimum=minimum):
            errors.append(f"{name} 长度不足或仍为示例值")
    if settings.wechat_dev_mock:
        errors.append("生产环境必须关闭 WECHAT_DEV_MOCK")
    if settings.feishu_dev_mock:
        errors.append("生产环境必须关闭 FEISHU_DEV_MOCK")
    for name, value in (
        ("WECHAT_APP_ID", settings.wechat_app_id),
        ("WECHAT_APP_SECRET", settings.wechat_app_secret),
        ("FEISHU_APP_ID", settings.feishu_app_id),
        ("FEISHU_APP_SECRET", settings.feishu_app_secret),
        ("FEISHU_APP_TOKEN", settings.feishu_app_token),
        ("FEISHU_TABLE_ID", settings.feishu_table_id),
    ):
        if not value:
            errors.append(f"{name} 未配置")
    oauth_uri = urlparse(settings.wechat_oauth_redirect_uri)
    if oauth_uri.scheme != "https" or (parsed.netloc and oauth_uri.netloc != parsed.netloc):
        errors.append("WECHAT_OAUTH_REDIRECT_URI 必须使用 HTTPS 并与 APP_BASE_URL 使用同一可信域名")
    origins = settings.cors_origin_list
    if not origins or "*" in origins or any("localhost" in origin or not origin.startswith("https://") for origin in origins):
        errors.append("CORS_ORIGINS 必须配置为生产 HTTPS 域名且不能使用通配符")
    if env.get("SEED_DEMO", "false").lower() == "true":
        errors.append("生产环境不得启用 SEED_DEMO")
    database_password = env.get("POSTGRES_PASSWORD", "")
    if _unsafe_secret(database_password, minimum=16):
        errors.append("POSTGRES_PASSWORD 长度不足或仍为示例值")
    if settings.auto_create_schema:
        errors.append("生产环境必须设置 AUTO_CREATE_SCHEMA=false，仅允许 Alembic 管理结构")
    if not settings.log_json:
        warnings.append("建议生产环境设置 LOG_JSON=true 以便日志采集")
    storage_backend = settings.object_storage_backend.lower()
    if storage_backend not in {"local", "s3"}:
        errors.append("OBJECT_STORAGE_BACKEND 仅支持 local 或 s3")
    if storage_backend == "s3":
        for name, value in (
            ("S3_ACCESS_KEY_ID", settings.s3_access_key_id),
            ("S3_SECRET_ACCESS_KEY", settings.s3_secret_access_key),
            ("S3_BUCKET", settings.s3_bucket),
        ):
            if not value:
                errors.append(f"{name} 未配置")
    else:
        warnings.append("生产环境仍使用本地对象存储，建议切换私有 S3/COS/OSS 并配置异地备份")
    if not settings.trusted_host_list or "*" in settings.trusted_host_list:
        errors.append("TRUSTED_HOSTS 必须配置明确域名，不能使用通配符")
    elif parsed.hostname and parsed.hostname not in settings.trusted_host_list:
        errors.append("TRUSTED_HOSTS 必须包含 APP_BASE_URL 的域名")
    return ProductionValidation(tuple(errors), tuple(warnings))

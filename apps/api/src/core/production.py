from __future__ import annotations

import ipaddress
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


def _valid_trusted_proxy_cidr(value: str) -> bool:
    """Accept exactly one explicit CIDR network and nothing else."""

    candidate = value.strip()
    if not candidate or "/" not in candidate or any(ch.isspace() for ch in candidate):
        return False
    try:
        network = ipaddress.ip_network(candidate, strict=False)
    except ValueError:
        return False
    if network.prefixlen == 0:
        return False
    return candidate == network.with_prefixlen


def validate_production_settings(settings: Settings, environ: dict[str, str] | None = None) -> ProductionValidation:
    env = environ or dict(os.environ)
    errors: list[str] = []
    warnings: list[str] = []
    if settings.app_env.lower() != "production":
        errors.append("APP_ENV 必须设置为 production")
    if not settings.app_version.startswith("1.2."):
        errors.append("APP_VERSION 必须是 V1.2 正式或补丁版本")
    parsed = urlparse(settings.app_base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append("APP_BASE_URL 必须使用有效 HTTPS 域名")
    if not settings.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        errors.append("生产环境 DATABASE_URL 必须使用 PostgreSQL")
    for name, value, minimum in (
        ("JWT_SECRET", settings.jwt_secret, 32),
        ("FIELD_ENCRYPTION_KEY", settings.field_encryption_key, 32),
        ("PHONE_HASH_SECRET", settings.phone_hash_secret, 24),
        ("PHONE_FINGERPRINT_SECRET", settings.phone_fingerprint_secret, 32),
    ):
        if _unsafe_secret(value, minimum=minimum):
            errors.append(f"{name} 长度不足、未显式配置或仍为示例值")
    if settings.phone_fingerprint_secret and settings.phone_fingerprint_secret == settings.phone_hash_secret:
        errors.append("PHONE_FINGERPRINT_SECRET 必须与 PHONE_HASH_SECRET 独立")
    if settings.wechat_dev_mock:
        errors.append("生产环境必须关闭 WECHAT_DEV_MOCK")
    for name, value in (
        ("WECHAT_APP_ID", settings.wechat_app_id),
        ("WECHAT_APP_SECRET", settings.wechat_app_secret),
    ):
        if not value:
            errors.append(f"{name} 未配置")
    if settings.feishu_dev_mock:
        errors.append("生产环境必须关闭 FEISHU_DEV_MOCK")
    if settings.feishu_enabled:
        for name, value in (
            ("FEISHU_APP_ID", settings.feishu_app_id),
            ("FEISHU_APP_SECRET", settings.feishu_app_secret),
            ("FEISHU_APP_TOKEN", settings.feishu_app_token),
            ("FEISHU_TABLE_ID", settings.feishu_table_id),
        ):
            if not value:
                errors.append(f"FEISHU_ENABLED=true 时 {name} 必须配置")
    elif any(
        (
            settings.feishu_app_id,
            settings.feishu_app_secret,
            settings.feishu_app_token,
            settings.feishu_table_id,
        )
    ):
        warnings.append("FEISHU_ENABLED=false，但仍存在飞书凭据；建议移除无效生产密钥")
    oauth_uri = urlparse(settings.wechat_oauth_redirect_uri)
    if oauth_uri.scheme != "https" or (parsed.netloc and oauth_uri.netloc != parsed.netloc):
        errors.append("WECHAT_OAUTH_REDIRECT_URI 必须使用 HTTPS 并与 APP_BASE_URL 使用同一可信域名")
    origins = settings.cors_origin_list
    if not origins or "*" in origins or any("localhost" in origin or not origin.startswith("https://") for origin in origins):
        errors.append("CORS_ORIGINS 必须配置为生产 HTTPS 域名且不能使用通配符")
    if env.get("SEED_DEMO", "false").lower() == "true":
        errors.append("生产环境不得启用 SEED_DEMO")
    trusted_proxy_cidr = env.get("TRUSTED_PROXY_CIDR", "127.0.0.1/32").strip()
    if not _valid_trusted_proxy_cidr(trusted_proxy_cidr):
        errors.append("TRUSTED_PROXY_CIDR 必须是单一、规范、非全网段的有效 CIDR，禁止额外指令或尾随内容")
    # M-B：生产拓扑的 nginx 会强制覆写 x-real-ip；若部署方忘设该开关，API
    # 会把所有请求的客户端 IP 记为反代内网地址——审计溯源全部失真且是静默
    # 失败，必须显式声明并强制为 true（docker-compose.prod.yml 已固定注入）。
    trust_proxy_headers = env.get("TRUST_PROXY_HEADERS", "").strip().lower()
    if trust_proxy_headers not in {"true", "false"}:
        errors.append("TRUST_PROXY_HEADERS 必须显式设置为 true/false，不得缺省")
    elif trust_proxy_headers != "true":
        errors.append(
            "标准生产拓扑的 nginx 会强制覆写 x-real-ip，必须设置 TRUST_PROXY_HEADERS=true，"
            "否则审计 IP 将恒为反代内网地址，安全事件无法溯源"
        )
    database_password = env.get("POSTGRES_PASSWORD", "")
    if _unsafe_secret(database_password, minimum=16):
        errors.append("POSTGRES_PASSWORD 长度不足或仍为示例值")
    if settings.auto_create_schema:
        errors.append("生产环境必须设置 AUTO_CREATE_SCHEMA=false，仅允许 Alembic 管理结构")
    if settings.legacy_write_enabled:
        errors.append("生产环境必须设置 LEGACY_WRITE_ENABLED=false，禁止 V1.0.1 历史流程继续写入")
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
            ("S3_REGION", settings.s3_region),
        ):
            if not value:
                errors.append(f"{name} 未配置")
        if settings.s3_endpoint_url:
            endpoint = urlparse(settings.s3_endpoint_url)
            if endpoint.scheme != "https" or not endpoint.netloc:
                errors.append("S3_ENDPOINT_URL 自定义地址必须使用有效 HTTPS URL；AWS S3 可留空使用默认区域端点")
            elif endpoint.hostname and endpoint.hostname.endswith(".myqcloud.com"):
                expected_host = f"cos.{settings.s3_region}.myqcloud.com"
                if endpoint.hostname != expected_host:
                    errors.append("腾讯云 COS 的 S3_ENDPOINT_URL 必须与 S3_REGION 对应")
                bucket_name, separator, app_id = settings.s3_bucket.rpartition("-")
                if not separator or not bucket_name or not app_id.isdigit():
                    errors.append("腾讯云 COS 的 S3_BUCKET 必须使用完整 BucketName-APPID")
    else:
        warnings.append("生产环境仍使用本地对象存储，正式全量前应切换私有 S3/COS/OSS 或完成异地备份与恢复演练")
    if not settings.trusted_host_list or "*" in settings.trusted_host_list:
        errors.append("TRUSTED_HOSTS 必须配置明确域名，不能使用通配符")
    elif parsed.hostname and parsed.hostname not in settings.trusted_host_list:
        errors.append("TRUSTED_HOSTS 必须包含 APP_BASE_URL 的域名")
    return ProductionValidation(tuple(errors), tuple(warnings))

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "众墅之家客资平台"
    app_base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./zhongshu.db"
    jwt_secret: str = "dev-change-me-at-least-32-characters-long"
    jwt_expire_minutes: int = 1440
    field_encryption_key: str = "dev-only-key-change-in-production"
    phone_hash_secret: str = "dev-phone-hash-secret"
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    wechat_oauth_redirect_uri: str = "http://localhost:8000/api/v1/auth/wechat/callback"
    wechat_oauth_scope: str = "snsapi_base"
    wechat_dev_mock: bool = True
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_app_token: str = ""
    feishu_table_id: str = ""
    feishu_dev_mock: bool = True
    feishu_field_mapping_json: str = ""
    feishu_sync_page_size: int = 200
    feishu_sync_max_pages: int = 100
    feishu_writeback_enabled: bool = True
    object_storage_backend: str = "local"
    object_storage_dir: str = "./storage"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket: str = "zhongshu-private"
    s3_region: str = "ap-singapore-1"
    cors_origins: str = "http://localhost:8000"
    low_points_warning_threshold: int = 1000
    assignment_reminder_hours: int = 24
    assignment_expire_hours: int = 48
    return_window_hours: int = 48
    first_followup_hours: int = 48

    @field_validator("object_storage_dir")
    @classmethod
    def normalize_storage_dir(cls, value: str) -> str:
        return str(Path(value))

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GUIDE = ROOT / "docs" / "runbooks" / "H5_ADMIN_CONFIG_GUIDE.md"


def test_guide_matches_current_storage_wechat_and_outbox_implementation() -> None:
    text = GUIDE.read_text(encoding="utf-8")

    for expected in (
        "375 是设计基准，不是固定宽度",
        "OBJECT_STORAGE_BACKEND=s3",
        "S3_ENDPOINT_URL=https://cos.ap-shanghai.myqcloud.com",
        "S3_REGION=ap-shanghai",
        "BucketName-APPID",
        "SecretId",
        "SecretKey",
        "python scripts/check_object_storage.py --canary",
        "WECHAT_DEV_MOCK=false",
        "OpenID / UnionID",
        "wechat_template",
        "V12_ASSIGNMENT_DISPATCHED",
        "python scripts/run_jobs.py outbox --limit 100",
        "/api/v1/notifications/gate0",
        "MANUAL_ACTION_REQUIRED",
    ):
        assert expected in text

    for stale_or_incorrect in (
        "REDIS_URL",
        "\nAPP_SECRET=",
        "https://s3-compatible.example.com",
        "S3_REGION=replace-with-region",
        "Outbox 或调度器把消息投递到飞书",
    ):
        assert stale_or_incorrect not in text


def test_guide_states_external_gates_and_wechat_login_boundary() -> None:
    text = GUIDE.read_text(encoding="utf-8")

    for expected in (
        "已实现",
        "待外部配置",
        "尚未实现",
        "不是微信号",
        "公众号网页 OAuth",
        "PC 端微信扫码登录",
        "真实微信公众号",
        "真实对象存储",
    ):
        assert expected in text


def test_example_env_files_keep_hejiameizhai_brand_and_current_version() -> None:
    development = (ROOT / ".env.example").read_text(encoding="utf-8")
    production = (ROOT / ".env.docker.example").read_text(encoding="utf-8")

    for text in (development, production):
        assert "APP_NAME=合家美宅客资平台" in text
        assert "APP_VERSION=1.2.0" in text
        assert "APP_NAME=众墅之家客资平台" not in text
        assert "S3_ENDPOINT_URL=https://cos.ap-shanghai.myqcloud.com" in text
        assert "S3_REGION=ap-shanghai" in text


def test_runtime_defaults_target_tencent_cos_shanghai() -> None:
    config = (ROOT / "apps" / "api" / "src" / "core" / "config.py").read_text(encoding="utf-8")

    assert 's3_endpoint_url: str = "https://cos.ap-shanghai.myqcloud.com"' in config
    assert 's3_region: str = "ap-shanghai"' in config

"""N9 迁移对称性回归（PostgreSQL）：0008 invite_tokens.used_by_user_id。

CI main-release 的 postgres-migration 曾在 downgrade 0001 时失败：0001 以当前
ORM metadata create_all 建表时，无名外键被 PostgreSQL 自动命名为
invite_tokens_used_by_user_id_fkey，而 0008 downgrade 按硬编码名
fk_invite_tokens_used_by_user 删除约束，必然失配。

本测试复刻该路径（head -> 0001 -> head）并锁定两项修复：
- downgrade 以 inspector 实测名解析约束（兼容两种历史命名）；
- models.py 显式命名外键后，create_all 与迁移路径命名收敛。

无 PostgreSQL 时跳过；CI 通过 INVITE_MIGRATION_POSTGRES_TEST_URL 启用。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from apps.api.src.core.config import get_settings

ROOT = Path(__file__).resolve().parents[3]


def _postgres_url() -> str:
    return os.environ.get("INVITE_MIGRATION_POSTGRES_TEST_URL", "").strip()


pytestmark = pytest.mark.skipif(
    not _postgres_url(),
    reason="set INVITE_MIGRATION_POSTGRES_TEST_URL to run the PostgreSQL migration symmetry test",
)


def _alembic_config() -> Config:
    # 不加载 alembic.ini：避免 env.py 的 fileConfig 重置 pytest 日志配置；
    # script_location 以绝对路径解析，不依赖进程 cwd。
    config = Config()
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return config


def test_invite_used_by_migration_symmetry_on_postgresql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _postgres_url()
    probe = create_engine(database_url, pool_pre_ping=True)
    try:
        assert probe.dialect.name == "postgresql"
    finally:
        probe.dispose()

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        config = _alembic_config()
        # 起点幂等收敛到 head（CI 跑到此处时库已在 head，本地可为任意状态）。
        command.upgrade(config, "head")
        # 复刻 CI 失败路径：降级到 0001 触发 0008 downgrade 的 PostgreSQL 分支。
        command.downgrade(config, "0001_initial")
        command.upgrade(config, "head")

        engine = create_engine(database_url, pool_pre_ping=True)
        try:
            foreign_keys = [
                item
                for item in inspect(engine).get_foreign_keys("invite_tokens")
                if set(item.get("constrained_columns") or []) == {"used_by_user_id"}
            ]
            assert len(foreign_keys) == 1
            # 双路径命名收敛后，create_all 建出的约束与迁移显式名一致。
            assert foreign_keys[0]["name"] == "fk_invite_tokens_used_by_user"
            assert foreign_keys[0].get("referred_table") == "users"
        finally:
            engine.dispose()
    finally:
        get_settings.cache_clear()

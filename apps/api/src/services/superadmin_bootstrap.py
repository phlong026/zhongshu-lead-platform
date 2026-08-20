from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, Table, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.models import Role, User, UserRole
from .audit import write_audit
from .auth_service import create_internal_user
from .rbac import seed_rbac


_REQUIRED_TABLES = {
    "audit_logs",
    "permissions",
    "role_permissions",
    "roles",
    "user_roles",
    "users",
}
_BOOTSTRAP_METADATA_TABLES = {
    "alembic_version",
    "permissions",
    "role_permissions",
    "roles",
}
_ROOT = Path(__file__).resolve().parents[4]


class SuperadminBootstrapError(RuntimeError):
    """A safe, operator-facing reason why bootstrap did not run."""


@dataclass(frozen=True)
class SuperadminBootstrapResult:
    created: bool
    user_id: str
    username: str


def _expected_migration_heads() -> set[str]:
    config = Config(str(_ROOT / "alembic.ini"))
    return set(ScriptDirectory.from_config(config).get_heads())


def _require_migrated_schema(db: Session) -> set[str]:
    bind = db.get_bind()
    tables = set(inspect(bind).get_table_names())
    missing = sorted(_REQUIRED_TABLES - tables)
    if missing:
        raise SuperadminBootstrapError(
            "数据库未完成迁移，缺少必要表：" + ", ".join(missing)
        )
    if bind.dialect.name == "postgresql" and "alembic_version" not in tables:
        raise SuperadminBootstrapError("数据库未完成 Alembic 迁移")
    if "alembic_version" in tables:
        current_heads = set(
            db.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        )
        expected_heads = _expected_migration_heads()
        if current_heads != expected_heads:
            raise SuperadminBootstrapError(
                "数据库迁移版本不是当前 head："
                f"current={sorted(current_heads)}, expected={sorted(expected_heads)}"
            )
    return tables


def _acquire_bootstrap_lock(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtext('zhongshu.bootstrap.superadmin'))"
            )
        )


def _active_superadmin(db: Session) -> User | None:
    return db.scalar(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.code == "SUPER_ADMIN", User.status == "ACTIVE")
        .order_by(User.created_at)
        .limit(1)
    )


def _nonempty_application_tables(db: Session, tables: set[str]) -> list[str]:
    bind = db.get_bind()
    metadata = MetaData()
    nonempty: list[str] = []
    for table_name in sorted(tables - _BOOTSTRAP_METADATA_TABLES):
        table = Table(table_name, metadata, autoload_with=bind)
        if db.scalar(select(1).select_from(table).limit(1)) is not None:
            nonempty.append(table_name)
    return nonempty


def _validate_identity(username: str, display_name: str) -> tuple[str, str]:
    normalized_username = username.strip()
    normalized_display_name = display_name.strip()
    if normalized_username != username or not 2 <= len(normalized_username) <= 64:
        raise SuperadminBootstrapError("超级管理员账号长度必须为 2 到 64 位且首尾不能有空格")
    if normalized_display_name != display_name or not 1 <= len(normalized_display_name) <= 64:
        raise SuperadminBootstrapError("显示名称长度必须为 1 到 64 位且首尾不能有空格")
    return normalized_username, normalized_display_name


def _validate_password(password: str, username: str) -> None:
    if not 12 <= len(password) <= 128:
        raise SuperadminBootstrapError("密码长度必须为 12 到 128 位")
    requirements = (
        any(character.islower() for character in password),
        any(character.isupper() for character in password),
        any(character.isdigit() for character in password),
        any(not character.isalnum() for character in password),
    )
    if not all(requirements):
        raise SuperadminBootstrapError("密码必须同时包含大写字母、小写字母、数字和符号")
    if username.casefold() in password.casefold():
        raise SuperadminBootstrapError("密码不能包含超级管理员账号")


def bootstrap_superadmin(
    db: Session,
    *,
    username: str,
    password: str,
    display_name: str,
) -> SuperadminBootstrapResult:
    """Create the first superadmin in an otherwise empty migrated database."""

    try:
        tables = _require_migrated_schema(db)
        _acquire_bootstrap_lock(db)

        existing = _active_superadmin(db)
        if existing is not None:
            return SuperadminBootstrapResult(
                created=False,
                user_id=existing.id,
                username=existing.username or "",
            )

        nonempty_tables = _nonempty_application_tables(db, tables)
        if nonempty_tables:
            raise SuperadminBootstrapError(
                "数据库已存在用户或业务数据但没有有效超级管理员，"
                "拒绝通过初始化脚本旁路提权；非空表："
                + ", ".join(nonempty_tables)
            )

        normalized_username, normalized_display_name = _validate_identity(
            username,
            display_name,
        )
        _validate_password(password, normalized_username)

        seed_rbac(db)
        user = create_internal_user(
            db,
            username=normalized_username,
            password=password,
            display_name=normalized_display_name,
            role_code="SUPER_ADMIN",
        )
        write_audit(
            db,
            principal=None,
            action="SYSTEM_SUPERADMIN_BOOTSTRAP",
            resource_type="user",
            resource_id=user.id,
            after={
                "username": user.username,
                "display_name": user.display_name,
                "role": "SUPER_ADMIN",
                "status": user.status,
            },
            metadata={"source": "bootstrap_superadmin"},
        )
        db.flush()
        return SuperadminBootstrapResult(
            created=True,
            user_id=user.id,
            username=user.username or "",
        )
    except SuperadminBootstrapError:
        raise
    except SQLAlchemyError as exc:
        raise SuperadminBootstrapError(
            "数据库初始化检查失败，请确认迁移已完成且数据库可写"
        ) from exc

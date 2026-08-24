from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.core.models import Assignment, AuditLog, Company, Lead, PointsLedger, User
from apps.api.src.core.security import verify_password
from apps.api.src.services.auth_service import create_internal_user
from apps.api.src.services.superadmin_bootstrap import (
    SuperadminBootstrapError,
    bootstrap_superadmin,
)
from scripts import bootstrap_superadmin as bootstrap_cli


STRONG_PASSWORD = "Local-Only-Root9!"


def test_bootstrap_creates_only_the_first_active_superadmin_and_audit(db: Session) -> None:
    result = bootstrap_superadmin(
        db,
        username="rootadmin",
        password=STRONG_PASSWORD,
        display_name="平台超级管理员",
    )
    db.commit()

    user = db.get(User, result.user_id)
    assert result.created is True
    assert user is not None
    assert user.username == "rootadmin"
    assert user.status == "ACTIVE"
    assert [role.code for role in user.roles] == ["SUPER_ADMIN"]
    assert verify_password(STRONG_PASSWORD, user.password_hash or "")

    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "SYSTEM_SUPERADMIN_BOOTSTRAP",
            AuditLog.resource_id == user.id,
        )
    )
    assert audit is not None
    serialized_audit = str(
        {
            "before": audit.before_json,
            "after": audit.after_json,
            "metadata": audit.metadata_json,
        }
    )
    assert STRONG_PASSWORD not in serialized_audit
    assert user.password_hash not in serialized_audit

    assert db.scalar(select(func.count(Company.id))) == 0
    assert db.scalar(select(func.count(Lead.id))) == 0
    assert db.scalar(select(func.count(Assignment.id))) == 0
    assert db.scalar(select(func.count(PointsLedger.id))) == 0


def test_bootstrap_is_idempotent_without_resetting_password_or_session(db: Session) -> None:
    first = bootstrap_superadmin(
        db,
        username="rootadmin",
        password=STRONG_PASSWORD,
        display_name="平台超级管理员",
    )
    db.commit()
    original = db.get(User, first.user_id)
    assert original is not None
    original_hash = original.password_hash
    original_session_version = original.session_version
    db.add(
        Company(
            code="AFTER-BOOTSTRAP",
            name="初始化后的业务数据",
            status="ACTIVE",
            level_code="V1",
        )
    )
    db.commit()

    second = bootstrap_superadmin(
        db,
        username="ignored-on-repeat",
        password="Another-Strong9!Password",
        display_name="不会覆盖",
    )
    db.commit()
    db.expire_all()

    current = db.get(User, first.user_id)
    assert second.created is False
    assert second.user_id == first.user_id
    assert db.scalar(select(func.count(User.id))) == 1
    assert current is not None
    assert current.password_hash == original_hash
    assert current.session_version == original_session_version
    assert current.display_name == "平台超级管理员"
    assert db.scalar(select(func.count(AuditLog.id))) == 1


def test_bootstrap_refuses_a_nonempty_database_without_superadmin(db: Session) -> None:
    create_internal_user(
        db,
        username="operation",
        password="Operation-Strong9!",
        display_name="运营",
        role_code="OPERATION",
    )
    db.commit()

    with pytest.raises(SuperadminBootstrapError, match="数据库已存在用户"):
        bootstrap_superadmin(
            db,
            username="rootadmin",
            password=STRONG_PASSWORD,
            display_name="平台超级管理员",
        )
    db.rollback()

    users = db.scalars(select(User)).all()
    assert [user.username for user in users] == ["operation"]
    assert all("SUPER_ADMIN" not in {role.code for role in user.roles} for user in users)


def test_bootstrap_refuses_business_data_even_when_users_are_empty(db: Session) -> None:
    db.add(
        Company(
            code="EXISTING-COMPANY",
            name="已有业务数据",
            status="ACTIVE",
            level_code="V1",
        )
    )
    db.commit()

    with pytest.raises(SuperadminBootstrapError, match="数据库已存在"):
        bootstrap_superadmin(
            db,
            username="rootadmin",
            password=STRONG_PASSWORD,
            display_name="平台超级管理员",
        )
    db.rollback()

    assert db.scalar(select(func.count(User.id))) == 0
    assert db.scalar(select(func.count(AuditLog.id))) == 0


@pytest.mark.parametrize(
    "password",
    [
        "short7",
        "x" * 129,
    ],
    ids=[
        "below-minimum",
        "above-maximum",
    ],
)
def test_bootstrap_rejects_out_of_range_passwords(db: Session, password: str) -> None:
    with pytest.raises(SuperadminBootstrapError, match="密码"):
        bootstrap_superadmin(
            db,
            username="rootadmin",
            password=password,
            display_name="平台超级管理员",
        )
    db.rollback()
    assert db.scalar(select(func.count(User.id))) == 0


def test_bootstrap_fails_closed_when_schema_is_not_migrated(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'unmigrated.db'}")
    factory = sessionmaker(bind=engine, class_=Session)
    with factory() as db:
        with pytest.raises(SuperadminBootstrapError, match="数据库未完成迁移"):
            bootstrap_superadmin(
                db,
                username="rootadmin",
                password=STRONG_PASSWORD,
                display_name="平台超级管理员",
            )
    assert inspect(engine).get_table_names() == []
    engine.dispose()


def _upgrade_to_head(database_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_bootstrap_works_after_alembic_upgrade(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migrated.db'}"
    _upgrade_to_head(database_url)
    engine = create_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    with factory() as db:
        result = bootstrap_superadmin(
            db,
            username="rootadmin",
            password=STRONG_PASSWORD,
            display_name="平台超级管理员",
        )
        db.commit()
        assert result.created is True
        assert db.scalar(select(func.count(User.id))) == 1
        assert db.scalar(
            select(AuditLog).where(AuditLog.action == "SYSTEM_RBAC_SYNC")
        ) is not None
    engine.dispose()


def test_bootstrap_rejects_a_stale_alembic_revision(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'stale-revision.db'}"
    _upgrade_to_head(database_url)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num = '0004_v12_reward_rule_snapshot'")
        )

    factory = sessionmaker(bind=engine, class_=Session)
    with factory() as db:
        with pytest.raises(SuperadminBootstrapError, match="迁移版本"):
            bootstrap_superadmin(
                db,
                username="rootadmin",
                password=STRONG_PASSWORD,
                display_name="平台超级管理员",
            )
    engine.dispose()


def test_cli_uses_hidden_confirmation_and_has_no_password_argument(db: Session, capsys) -> None:
    db.commit()
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False, class_=Session)
    supplied = iter([STRONG_PASSWORD, STRONG_PASSWORD])
    prompts: list[str] = []

    def read_password(prompt: str) -> str:
        prompts.append(prompt)
        return next(supplied)

    result = bootstrap_cli.main(
        ["--username", "rootadmin", "--display-name", "平台超级管理员"],
        session_factory=factory,
        password_reader=read_password,
    )

    output = capsys.readouterr()
    options = {
        option
        for action in bootstrap_cli.build_parser()._actions
        for option in action.option_strings
    }
    assert result == 0
    assert prompts == ["输入超级管理员密码: ", "再次输入密码: "]
    assert "--password" not in options
    assert STRONG_PASSWORD not in output.out
    assert STRONG_PASSWORD not in output.err
    assert '"status": "created"' in output.out


def test_cli_does_not_create_schema_seed_demo_or_touch_wechat() -> None:
    source = Path("scripts/bootstrap_superadmin.py").read_text(encoding="utf-8")
    assert "init_database" not in source
    assert "seed_demo" not in source
    assert "alembic" not in source.lower()
    assert "wechat" not in source.lower()


def test_bootstrap_accepts_eight_characters_without_composition(db: Session) -> None:
    result = bootstrap_superadmin(
        db,
        username="rootadmin",
        password="rootadmin",
        display_name="平台超级管理员",
    )
    db.commit()

    user = db.get(User, result.user_id)
    assert user is not None
    assert verify_password("rootadmin", user.password_hash or "")

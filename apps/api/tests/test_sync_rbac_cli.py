from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.core.database import Base
from apps.api.src.core.models import AuditLog, Permission, Role, RolePermission
from apps.api.src.services.rbac import seed_rbac
from scripts import sync_rbac


ROOT = Path(__file__).resolve().parents[3]


def _session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rbac-sync.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    with factory() as db:
        seed_rbac(db, source="test_setup")
        operation = db.scalar(select(Role).where(Role.code == "OPERATION"))
        assert operation is not None
        stale = Permission(
            code="legacy.cli.permission",
            name="legacy.cli.permission",
            module="legacy",
            sensitive=True,
        )
        db.add(stale)
        db.flush()
        db.add(RolePermission(role_id=operation.id, permission_id=stale.id))
        db.commit()
    return engine, factory


def _operation_permissions(factory) -> set[str]:
    with factory() as db:
        operation = db.scalar(select(Role).where(Role.code == "OPERATION"))
        assert operation is not None
        return set(
            db.scalars(
                select(Permission.code)
                .join(
                    RolePermission,
                    RolePermission.permission_id == Permission.id,
                )
                .where(RolePermission.role_id == operation.id)
            ).all()
        )


def test_cli_defaults_to_read_only_preview(
    tmp_path: Path,
    capsys,
) -> None:
    engine, factory = _session_factory(tmp_path)
    try:
        exit_code = sync_rbac.main([], session_factory=factory)

        payload = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert payload["mode"] == "preview"
        assert payload["result"]["removed_count"] == 1
        assert "legacy.cli.permission" in _operation_permissions(factory)
        with factory() as db:
            assert db.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.action == "SYSTEM_RBAC_SYNC"
                )
            ) == 0
    finally:
        engine.dispose()


def test_cli_apply_records_the_exact_sync_and_is_idempotent(
    tmp_path: Path,
    capsys,
) -> None:
    engine, factory = _session_factory(tmp_path)
    try:
        first_exit = sync_rbac.main(
            ["--apply", "--source", "pytest"],
            session_factory=factory,
        )
        first_payload = json.loads(capsys.readouterr().out)
        second_exit = sync_rbac.main(
            ["--apply", "--source", "pytest"],
            session_factory=factory,
        )
        second_payload = json.loads(capsys.readouterr().out)

        assert first_exit == 0
        assert first_payload["mode"] == "apply"
        assert first_payload["result"]["removed_count"] == 1
        assert second_exit == 0
        assert second_payload["result"]["changed"] is False
        assert "legacy.cli.permission" not in _operation_permissions(factory)
        with factory() as db:
            audit = db.scalar(
                select(AuditLog).where(AuditLog.action == "SYSTEM_RBAC_SYNC")
            )
            assert audit is not None
            assert audit.metadata_json == {"mode": "apply", "source": "pytest"}
            assert audit.after_json == first_payload["result"]
            assert db.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.action == "SYSTEM_RBAC_SYNC"
                )
            ) == 1
    finally:
        engine.dispose()


def test_cli_entrypoint_keeps_machine_readable_json_on_stdout(
    tmp_path: Path,
) -> None:
    engine, factory = _session_factory(tmp_path)
    env = os.environ.copy()
    env["APP_ENV"] = "test"
    env["DATABASE_URL"] = engine.url.render_as_string(hide_password=False)
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/sync_rbac.py",
                "--apply",
                "--source",
                "subprocess_test",
            ],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(completed.stdout)
        assert payload["mode"] == "apply"
        assert payload["result"]["removed_count"] == 1
        assert "fixed RBAC matrix synchronized" in completed.stderr
        assert "legacy.cli.permission" not in _operation_permissions(factory)
    finally:
        engine.dispose()

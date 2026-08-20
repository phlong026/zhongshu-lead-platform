from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.core.errors import AppError
from apps.api.src.core.models import Role, User
from apps.api.src.services.auth_service import create_internal_user
from apps.api.src.services.internal_user_management import update_internal_roles


def test_postgres_serializes_concurrent_superadmin_demotions() -> None:
    database_url = os.environ.get("V12_E2E_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("requires the disposable V12 E2E PostgreSQL database")

    engine = create_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.skip("PostgreSQL advisory lock coverage only")
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    suffix = uuid4().hex[:10]
    usernames = [f"concurrent_super_a_{suffix}", f"concurrent_super_b_{suffix}"]
    try:
        with factory() as db:
            for existing in db.scalars(
                select(User).join(User.roles).where(Role.code == "SUPER_ADMIN")
            ).unique():
                existing.status = "DISABLED"
            users = [
                create_internal_user(
                    db,
                    username=username,
                    password="Concurrency-Only9!",
                    display_name=username,
                    role_code="SUPER_ADMIN",
                )
                for username in usernames
            ]
            db.commit()
            user_ids = [user.id for user in users]

        barrier = Barrier(2)

        def demote(user_id: str) -> str:
            with factory() as db:
                barrier.wait(timeout=10)
                try:
                    update_internal_roles(
                        db,
                        user_id=user_id,
                        role_codes=["OWNER"],
                    )
                    db.commit()
                    return "UPDATED"
                except AppError as exc:
                    db.rollback()
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(demote, user_ids))

        assert sorted(outcomes) == ["LAST_SUPER_ADMIN_REQUIRED", "UPDATED"]
        with factory() as db:
            active_ids = set(
                db.scalars(
                    select(User.id)
                    .join(User.roles)
                    .where(Role.code == "SUPER_ADMIN", User.status == "ACTIVE")
                ).all()
            )
            assert active_ids == set(user_ids) - {
                user_id
                for user_id, outcome in zip(user_ids, outcomes, strict=True)
                if outcome == "UPDATED"
            }
    finally:
        engine.dispose()

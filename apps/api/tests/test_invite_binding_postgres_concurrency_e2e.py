"""PostgreSQL-only concurrency coverage for invite binding (module-01 P0-05/P0-06).

SQLite cannot exercise row locks (`with_for_update` is a no-op there), so the
atomic primary-account claim and the single-valid-invite invariant are verified
against the disposable V12 E2E PostgreSQL database only; skips do not count as
passing the lock acceptance gate.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.core.errors import AppError
from apps.api.src.core.models import Company, InviteToken, User, WechatIdentity
from apps.api.src.core.security import hash_token
from apps.api.src.core.time import utcnow
from apps.api.src.services.auth_service import create_company_invite, login_or_bind_wechat


def _postgres_factory():
    database_url = os.environ.get("V12_E2E_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("requires the disposable V12 E2E PostgreSQL database")
    engine = create_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.skip("invite binding row-lock coverage is PostgreSQL only")
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    return engine, factory


def test_concurrent_binding_cannot_double_claim_primary_account() -> None:
    engine, factory = _postgres_factory()
    suffix = uuid4().hex[:10]
    try:
        with factory() as db:
            company = Company(code=f"IVB-{suffix}", name="邀请并发绑定公司", status="ACTIVE")
            db.add(company)
            db.flush()
            company_id = company.id
            legacy_raws = []
            for index in range(2):
                # 直插两条历史遗留邀请，模拟 P0-06 唯一性收口之前的数据
                raw = f"ivb-legacy-{suffix}-{index}"
                db.add(
                    InviteToken(
                        token_hash=hash_token(raw),
                        company_id=company_id,
                        expires_at=utcnow() + timedelta(hours=1),
                    )
                )
                legacy_raws.append(raw)
            db.commit()

        barrier = Barrier(2)

        def bind(raw: str) -> str:
            # barrier 位于连接 checkout 之前，避免持锁等待造成死锁
            with factory() as db:
                barrier.wait(timeout=10)
                try:
                    user, _ = login_or_bind_wechat(
                        db,
                        openid=f"ivb-openid-{raw}",
                        nickname="并发绑定用户",
                        invite_token=raw,
                    )
                    db.commit()
                    return user.id
                except AppError as exc:
                    db.rollback()
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(bind, legacy_raws))

        winners = [outcome for outcome in outcomes if not outcome.startswith("AUTH_")]
        losers = [outcome for outcome in outcomes if outcome.startswith("AUTH_")]
        assert len(winners) == 1, outcomes
        assert losers == ["AUTH_COMPANY_ALREADY_BOUND"], outcomes

        with factory() as db:
            company_row = db.get(Company, company_id)
            assert company_row is not None
            assert company_row.primary_user_id == winners[0]
            user_count = db.scalar(
                select(func.count(User.id)).where(User.company_id == company_id)
            )
            identity_count = db.scalar(
                select(func.count(WechatIdentity.id))
                .join(User, User.id == WechatIdentity.user_id)
                .where(User.company_id == company_id)
            )
            assert user_count == 1
            assert identity_count == 1
            invites = db.scalars(
                select(InviteToken).where(InviteToken.company_id == company_id)
            ).all()
            used = [invite for invite in invites if invite.used_at is not None]
            assert len(used) == 1
    finally:
        engine.dispose()


def test_concurrent_invite_creation_keeps_single_valid_invite() -> None:
    engine, factory = _postgres_factory()
    suffix = uuid4().hex[:10]
    try:
        with factory() as db:
            company = Company(code=f"IVC-{suffix}", name="邀请并发创建公司", status="ACTIVE")
            db.add(company)
            db.commit()
            company_id = company.id

        barrier = Barrier(2)

        def create(_: int) -> str:
            # barrier 位于连接 checkout 之前，两个事务在行锁上串行化
            with factory() as db:
                barrier.wait(timeout=10)
                try:
                    _, raw, _ = create_company_invite(db, company_id, None, 24)
                    db.commit()
                    return raw
                except AppError as exc:
                    db.rollback()
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(create, range(2)))

        # 两次创建都成功；后提交者原子撤销先提交者，最终仅一条有效邀请
        assert all(not outcome.startswith(("AUTH_", "COMPANY_")) for outcome in outcomes)
        with factory() as db:
            invites = db.scalars(
                select(InviteToken).where(InviteToken.company_id == company_id)
            ).all()
            assert len(invites) == 2
            valid = [
                invite
                for invite in invites
                if invite.used_at is None
                and invite.revoked_at is None
                and invite.expires_at > utcnow()
            ]
            assert len(valid) == 1
    finally:
        engine.dispose()

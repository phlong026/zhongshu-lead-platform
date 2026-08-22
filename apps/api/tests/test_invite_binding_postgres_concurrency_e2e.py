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
from sqlalchemy import create_engine, func, select, update
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

def test_cross_concurrent_invite_creation_and_binding_no_deadlock() -> None:
    """I5：创建（公司→邀请）与绑定（修复后同为公司→邀请）必须同序加锁。

    修复前绑定路径先锁邀请再锁公司，与创建路径构成 AB-BA，PostgreSQL 会以
    deadlock detected (40P01) 终止一侧事务。修复后两侧都在公司行锁上串行化，
    任意交错都以业务结果收尾，且主账号占用不变量保持。
    """

    engine, factory = _postgres_factory()
    suffix = uuid4().hex[:10]
    try:
        with factory() as db:
            company = Company(code=f"IVX-{suffix}", name="交叉并发公司", status="ACTIVE")
            db.add(company)
            db.flush()
            company_id = company.id
            raw = f"ivx-invite-{suffix}"
            db.add(
                InviteToken(
                    token_hash=hash_token(raw),
                    company_id=company_id,
                    expires_at=utcnow() + timedelta(hours=1),
                )
            )
            db.commit()

        barrier = Barrier(2)

        def create(_: int) -> str:
            with factory() as db:
                barrier.wait(timeout=10)
                try:
                    _, new_raw, _ = create_company_invite(db, company_id, None, 24)
                    db.commit()
                    return new_raw
                except AppError as exc:
                    db.rollback()
                    return exc.code

        def bind(_: int) -> str:
            with factory() as db:
                barrier.wait(timeout=10)
                try:
                    user, _ = login_or_bind_wechat(
                        db,
                        openid=f"ivx-openid-{suffix}",
                        nickname="交叉绑定用户",
                        invite_token=raw,
                    )
                    db.commit()
                    return user.id
                except AppError as exc:
                    db.rollback()
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            create_future = pool.submit(create, 0)
            bind_future = pool.submit(bind, 0)
            outcomes = [create_future.result(timeout=30), bind_future.result(timeout=30)]

        # 两侧都收尾于业务结果； deadlock / OperationalError 会经 result() 重新抛出。
        create_outcome, bind_outcome = outcomes
        bind_won = not bind_outcome.startswith("AUTH_")
        if bind_won:
            # 绑定先完成：创建侧必须看到公司已绑定而拒绝
            assert create_outcome == "AUTH_COMPANY_ALREADY_BOUND", outcomes
        else:
            # 创建先完成：预置邀请被原子撤销，绑定侧必须看到邀请失效
            assert bind_outcome == "AUTH_INVITE_INVALID", outcomes

        with factory() as db:
            company_row = db.get(Company, company_id)
            assert company_row is not None
            if bind_won:
                assert company_row.primary_user_id == bind_outcome
            else:
                assert company_row.primary_user_id is None
            identity_count = db.scalar(
                select(func.count(WechatIdentity.id))
                .join(User, User.id == WechatIdentity.user_id)
                .where(User.company_id == company_id)
            )
            assert identity_count == (1 if bind_won else 0)
    finally:
        engine.dispose()



def test_concurrent_double_revoke_yields_exactly_one_success() -> None:
    """W1/I8：PG 行锁下并发重复撤销——恰好一个成功，另一个按 409 语义拒绝。"""
    engine, factory = _postgres_factory()
    suffix = uuid4().hex[:10]
    try:
        with factory() as db:
            company = Company(code=f"RVK-{suffix}", name="撤销并发公司", status="ACTIVE")
            db.add(company)
            db.flush()
            invite = InviteToken(
                token_hash=hash_token(f"rvk-{suffix}"),
                company_id=company.id,
                expires_at=utcnow() + timedelta(hours=1),
            )
            db.add(invite)
            db.commit()
            invite_id = invite.id

        barrier = Barrier(2)

        def revoke_once(session: Session) -> str:
            # revoke 路由逻辑镜像：行锁读取 → 生命周期校验 → 盖写 revoked_at。
            row = session.scalar(select(InviteToken).where(InviteToken.id == invite_id).with_for_update())
            assert row is not None
            if row.revoked_at is not None:
                session.rollback()
                return "INVITE_ALREADY_REVOKED"
            row.revoked_at = utcnow()
            session.commit()
            return "REVOKED"

        def worker() -> str:
            with factory() as session:
                barrier.wait(timeout=10)
                return revoke_once(session)

        with ThreadPoolExecutor(max_workers=2) as pool:
            # 先全部 submit 再等待：逐个 submit+.result() 会让首个 worker 卡在
            # Barrier 上等永不发出的第二个任务，整进程死锁。
            futures = [pool.submit(worker) for _ in range(2)]
            outcomes = sorted(future.result() for future in futures)
        assert outcomes == ["INVITE_ALREADY_REVOKED", "REVOKED"], outcomes

        with factory() as db:
            final = db.get(InviteToken, invite_id)
            assert final is not None
            assert final.revoked_at is not None
            assert final.used_at is None
    finally:
        engine.dispose()


def test_concurrent_revoke_and_consume_never_marks_used_invite_revoked() -> None:
    """W1/I8 红线：撤销与消费并发竞争的任何终态都不得同时落 used_at 与 revoked_at。"""
    engine, factory = _postgres_factory()
    suffix = uuid4().hex[:10]
    try:
        with factory() as db:
            company = Company(code=f"RVC-{suffix}", name="撤销消费竞争公司", status="ACTIVE")
            db.add(company)
            db.flush()
            invite = InviteToken(
                token_hash=hash_token(f"rvc-{suffix}"),
                company_id=company.id,
                expires_at=utcnow() + timedelta(hours=1),
            )
            db.add(invite)
            db.commit()
            invite_id = invite.id

        barrier = Barrier(2)

        def revoke_attempt(session: Session) -> str:
            row = session.scalar(select(InviteToken).where(InviteToken.id == invite_id).with_for_update())
            assert row is not None
            if row.used_at is not None or row.revoked_at is not None:
                session.rollback()
                return "REJECTED"
            row.revoked_at = utcnow()
            session.commit()
            return "REVOKED"

        def consume_attempt(session: Session) -> str:
            # _consume_invite 条件更新镜像：三个并发边界条件原样保留。
            rowcount = session.execute(
                update(InviteToken)
                .where(
                    InviteToken.id == invite_id,
                    InviteToken.used_at.is_(None),
                    InviteToken.revoked_at.is_(None),
                    InviteToken.expires_at > utcnow(),
                )
                .values(used_at=utcnow())
            ).rowcount
            session.commit()
            return "CONSUMED" if rowcount else "REJECTED"

        def run(fn) -> str:
            with factory() as session:
                barrier.wait(timeout=10)
                return fn(session)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, revoke_attempt), pool.submit(run, consume_attempt)]
            outcomes = sorted(future.result() for future in futures)
        # 两种合法收敛：撤销先行（消费被条件拒绝）或消费先行（撤销行锁后重读拒绝）。
        assert outcomes in (["CONSUMED", "REJECTED"], ["REJECTED", "REVOKED"]), outcomes

        with factory() as db:
            final = db.get(InviteToken, invite_id)
            assert final is not None
            # I8 红线：used_at 与 revoked_at 不得同时非空。
            assert not (final.used_at is not None and final.revoked_at is not None)
    finally:
        engine.dispose()

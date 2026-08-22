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
from sqlalchemy import create_engine, func, inspect, select, update
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.core.errors import AppError
from apps.api.src.core.models import Company, InviteToken, User, WechatIdentity
from apps.api.src.core.security import hash_token
from apps.api.src.core.time import utcnow
from apps.api.src.services.auth_service import create_company_invite, login_or_bind_wechat, revoke_company_invite


def _postgres_factory():
    database_url = os.environ.get("V12_E2E_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("requires the disposable V12 E2E PostgreSQL database")
    engine = create_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.skip("invite binding row-lock coverage is PostgreSQL only")
    # I21：本文件不建 schema 不 seed，可运行性依赖 lifecycle e2e 先跑
    # （run_v12_e2e 的 TARGET_TESTS 顺序契约）。对未迁移的空库显式 skip，
    # 而不是半途 ValueError 让整批 e2e 报错。
    if "invite_tokens" not in inspect(engine).get_table_names():
        engine.dispose()
        pytest.skip("database schema not initialized; run scripts/run_v12_e2e.py")
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
            # N4：直接调生产实现，不再维护路由逻辑镜像（镜像漂移=测了个寂寞）。
            try:
                revoke_company_invite(session, invite_id=invite_id, principal=None, request_id="e2e-double-revoke")
                return "REVOKED"
            except AppError as exc:
                session.rollback()
                return exc.code

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


def test_concurrent_same_openid_two_invites_replays_idempotent_login() -> None:
    """I14：同 openid 携不同邀请（不同公司）双并发——两事务在各自公司
    行锁上互不阻塞，双双走到 identity INSERT，后落库者撞 WechatIdentity.
    openid 唯一约束（同邀请/同公司双邀请分别在 _consume_invite 与主账号
    条件 UPDATE 处被拒，构不成 identity 竞态）。

    真实 callback 必传 signed state 中的 expected_company_id，败者重读
    winner 身份后按「已绑定其他公司」拒绝（保持转发误绑同款语义），
    而非以 winner 身份静默登录——修复前该竞态以 IntegrityError 穿透成
    409/500 裸 JSON。败者的半途写入（用户/身份/主账号占用/邀请消费）
    必须随 rollback 全部撤销。"""

    engine, factory = _postgres_factory()
    suffix = uuid4().hex[:10]
    try:
        company_ids = []
        raws = []
        with factory() as db:
            for index in range(2):
                company = Company(code=f"IVS-{suffix}-{index}", name=f"同微信并发公司{index}", status="ACTIVE")
                db.add(company)
                db.flush()
                company_ids.append(company.id)
                raw = f"ivs-invite-{suffix}-{index}"
                db.add(
                    InviteToken(
                        token_hash=hash_token(raw),
                        company_id=company.id,
                        expires_at=utcnow() + timedelta(hours=1),
                    )
                )
                raws.append(raw)
            db.commit()

        barrier = Barrier(2)

        def bind(pair: tuple[str, str]) -> str:
            raw, expected_company_id = pair
            with factory() as db:
                barrier.wait(timeout=10)
                try:
                    user, _ = login_or_bind_wechat(
                        db,
                        openid=f"ivs-openid-{suffix}",
                        nickname="同微信并发用户",
                        invite_token=raw,
                        expected_company_id=expected_company_id,
                    )
                    db.commit()
                    return user.id
                except AppError as exc:
                    db.rollback()
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(bind, (raw, company_id))
                for raw, company_id in zip(raws, company_ids)
            ]
            outcomes = [future.result(timeout=30) for future in futures]

        winners = [outcome for outcome in outcomes if not outcome.startswith("AUTH_")]
        losers = [outcome for outcome in outcomes if outcome.startswith("AUTH_")]
        # 一成功一拒绝：败者收敛为「已绑定其他公司」业务码，不泄漏裸异常
        assert len(winners) == 1, outcomes
        assert losers == ["AUTH_WECHAT_BOUND_OTHER_COMPANY"], outcomes
        winner_id = winners[0]

        with factory() as db:
            user_rows = db.scalars(
                select(User).where(User.company_id.in_(company_ids))
            ).all()
            assert [row.id for row in user_rows] == [winner_id]
            identity_count = db.scalar(
                select(func.count(WechatIdentity.id)).where(WechatIdentity.openid == f"ivs-openid-{suffix}")
            )
            assert identity_count == 1, "openid 唯一性保持"
            for company_id in company_ids:
                company_row = db.get(Company, company_id)
                assert company_row is not None
                invite = db.scalar(
                    select(InviteToken).where(InviteToken.company_id == company_id)
                )
                assert invite is not None
                if company_row.primary_user_id == winner_id:
                    assert invite.used_at is not None
                else:
                    # 败者的半途写入全部回滚：无主账号占用、邀请未消费
                    assert company_row.primary_user_id is None, outcomes
                    assert invite.used_at is None, outcomes
    finally:
        engine.dispose()
def test_concurrent_same_openid_same_invite_yields_business_rejection() -> None:
    """I14 边界：同一邀请被同 openid 双发——company 行锁串行化后，后到者
    在邀请消费处被条件 UPDATE 拒绝（AUTH_INVITE_INVALID 业务语义），
    不得泄漏裸异常，胜者数据完整。"""

    engine, factory = _postgres_factory()
    suffix = uuid4().hex[:10]
    try:
        with factory() as db:
            company = Company(code=f"IVT-{suffix}", name="同微信同邀请公司", status="ACTIVE")
            db.add(company)
            db.flush()
            company_id = company.id
            raw = f"ivt-invite-{suffix}"
            db.add(
                InviteToken(
                    token_hash=hash_token(raw),
                    company_id=company_id,
                    expires_at=utcnow() + timedelta(hours=1),
                )
            )
            db.commit()

        barrier = Barrier(2)

        def bind(_: int) -> str:
            with factory() as db:
                barrier.wait(timeout=10)
                try:
                    user, _ = login_or_bind_wechat(
                        db,
                        openid=f"ivt-openid-{suffix}",
                        nickname="同邀请并发用户",
                        invite_token=raw,
                    )
                    db.commit()
                    return user.id
                except AppError as exc:
                    db.rollback()
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(bind, i) for i in range(2)]
            outcomes = [future.result(timeout=30) for future in futures]

        winners = [outcome for outcome in outcomes if not outcome.startswith("AUTH_")]
        losers = [outcome for outcome in outcomes if outcome.startswith("AUTH_")]
        assert len(winners) == 1, outcomes
        assert losers == ["AUTH_INVITE_INVALID"], outcomes

        with factory() as db:
            company_row = db.get(Company, company_id)
            assert company_row is not None
            assert company_row.primary_user_id == winners[0]
            user_count = db.scalar(
                select(func.count(User.id)).where(User.company_id == company_id)
            )
            assert user_count == 1
            invite = db.scalar(
                select(InviteToken).where(InviteToken.company_id == company_id)
            )
            assert invite is not None
            assert invite.used_at is not None
            assert invite.revoked_at is None
    finally:
        engine.dispose()

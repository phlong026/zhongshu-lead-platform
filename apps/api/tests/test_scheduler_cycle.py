from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scripts.scheduler as scheduler
from apps.api.src.core.database import Base
from apps.api.src.core import auth_models, models  # noqa: F401
from apps.api.src.services.notification_service import enqueue_outbox
from apps.api.src.services.outbox_worker import process_outbox


@pytest.fixture()
def scheduler_session(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'scheduler.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(scheduler, "SessionLocal", factory)
    return factory


def _delivered_outbox(db):
    from apps.api.src.core.models import User, WechatIdentity

    user = User(display_name="N10收件人", status="ACTIVE")
    db.add(user)
    db.flush()
    db.add(WechatIdentity(openid="o-n10-cycle", user_id=user.id))
    item = enqueue_outbox(
        db, event_key="n10:cycle", event_type="ASSIGNMENT_DISPATCHED",
        aggregate_type="assignment", aggregate_id="1", payload={"user_id": user.id},
    )
    db.commit()
    assert process_outbox(db)["sent"] == 1  # dev mock 通道发送成功
    db.commit()
    return item.id


def test_slow_job_failure_does_not_roll_back_outbox_progress(scheduler_session, monkeypatch) -> None:
    """N10：outbox 进度必须先落库——慢任务异常不得回滚已发送状态，
    否则下一轮会向用户重发同一条通知。"""

    from apps.api.src.core.models import NotificationOutbox
    from apps.api.src.integrations import wechat as wechat_module

    monkeypatch.setattr(wechat_module.settings, "wechat_dev_mock", True)

    with scheduler_session() as db:
        item_id = _delivered_outbox(db)

    monkeypatch.setattr(scheduler, "run_assignment_timeouts_active", lambda db: 0)
    monkeypatch.setattr(scheduler, "run_low_points_warnings", lambda db: 0)
    monkeypatch.setattr(
        scheduler, "run_followup_overdue",
        lambda db: (_ for _ in ()).throw(RuntimeError("slow job boom")),
    )

    assert scheduler.run_cycle(run_slow_jobs=True, run_hourly_jobs=False) is False

    with scheduler_session() as db:
        item = db.get(NotificationOutbox, item_id)
        assert item.status == "SENT", "outbox 已发送状态被慢任务异常回滚"


def test_daily_binding_integrity_violations_raise_alert(scheduler_session, caplog) -> None:
    """N2：binding_integrity 接入 scheduler 日检——违规必须落 error 告警。"""

    import logging as _logging

    from apps.api.src.core.models import Company

    with scheduler_session() as db:
        db.add(
            Company(
                code="N2-DANGLING",
                name="悬空主账号公司",
                status="ACTIVE",
                primary_user_id="ghost-user-id",
            )
        )
        db.commit()

    with caplog.at_level(_logging.ERROR, logger="scheduler"):
        assert scheduler.run_cycle(run_slow_jobs=False, run_hourly_jobs=False, run_daily_jobs=True) is True

    alerts = [r for r in caplog.records if "binding integrity" in r.message]
    assert alerts, "绑定一致性违规必须落 error 级告警"
    assert "DANGLING_PRIMARY" in caplog.text


def test_daily_binding_integrity_runs_once_per_real_day() -> None:
    """scheduler 主循环每 30 秒 tick 一次，日检必须等于 24 小时。"""

    assert scheduler.DAILY_JOB_TICKS == 24 * 60 * 2

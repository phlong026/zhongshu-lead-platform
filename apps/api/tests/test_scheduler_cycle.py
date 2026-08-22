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

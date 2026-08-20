from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.src.core.database import Base
from apps.api.src.core.models_v12 import CalendarDay
from apps.api.src.services.workday_calendar import CalendarDayInput, WorkdayCalendarService


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_add_three_workdays_uses_shanghai_date_and_preserves_local_time(
    db: Session,
) -> None:
    service = WorkdayCalendarService(db)
    claimed_at = datetime(2026, 8, 7, 16, 30, tzinfo=timezone.utc)
    deadline = service.add_workdays(claimed_at, 3)
    assert deadline == datetime(2026, 8, 11, 16, 30, tzinfo=timezone.utc)


def test_aware_timestamp_uses_shanghai_business_date_across_midnight(
    db: Session,
) -> None:
    service = WorkdayCalendarService(db)
    friday_utc_but_saturday_in_china = datetime(
        2026,
        8,
        7,
        16,
        30,
        tzinfo=timezone.utc,
    )

    deadline = service.add_workdays(friday_utc_but_saturday_in_china, 1)

    assert deadline == datetime(2026, 8, 9, 16, 30, tzinfo=timezone.utc)


def test_explicit_holiday_overrides_weekday_fallback(db: Session) -> None:
    service = WorkdayCalendarService(db)
    service.upsert_day(CalendarDayInput(day=date(2026, 8, 10), is_workday=False, holiday_name="测试节假日"))
    db.commit()
    deadline = service.add_workdays(datetime(2026, 8, 7, 9, 0), 3)
    assert deadline == datetime(2026, 8, 13, 9, 0)


def test_makeup_saturday_counts_as_workday(db: Session) -> None:
    service = WorkdayCalendarService(db)
    service.upsert_day(CalendarDayInput(day=date(2026, 8, 8), is_workday=True, holiday_name="调休工作日"))
    db.commit()
    deadline = service.add_workdays(datetime(2026, 8, 7, 9, 0), 1)
    assert deadline == datetime(2026, 8, 8, 9, 0)


def test_import_rejects_duplicate_dates_before_partial_success(db: Session) -> None:
    service = WorkdayCalendarService(db)
    day = CalendarDayInput(day=date(2026, 10, 1), is_workday=False)
    with pytest.raises(ValueError, match="duplicate calendar day"):
        service.import_days([day, day])
    db.rollback()
    assert db.get(CalendarDay, day.day) is None


def test_workdays_between_excludes_start_and_can_exclude_end(db: Session) -> None:
    service = WorkdayCalendarService(db)
    assert service.workdays_between(date(2026, 8, 7), date(2026, 8, 12)) == 3
    assert service.workdays_between(date(2026, 8, 7), date(2026, 8, 12), include_end=False) == 2

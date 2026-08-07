from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.models_v12 import CalendarDay


@dataclass(frozen=True, slots=True)
class CalendarDayInput:
    day: date
    is_workday: bool
    holiday_name: str | None = None
    source: str = "MANUAL"
    version: int = 1


class WorkdayCalendarService:
    """Single source of truth for appeal and reward deadlines.

    Missing dates fall back to Monday-Friday. Explicit rows always override
    the fallback, including official holidays and makeup workdays.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_day(self, day: date) -> CalendarDay | None:
        return self.db.get(CalendarDay, day)

    def is_workday(self, day: date) -> bool:
        item = self.get_day(day)
        if item is not None:
            return bool(item.is_workday)
        return day.weekday() < 5

    def add_workdays(self, moment: datetime, count: int) -> datetime:
        if count < 0:
            return self.subtract_workdays(moment, -count)
        if count == 0:
            return moment
        cursor = moment
        remaining = count
        while remaining:
            cursor += timedelta(days=1)
            if self.is_workday(cursor.date()):
                remaining -= 1
        return cursor

    def subtract_workdays(self, moment: datetime, count: int) -> datetime:
        if count < 0:
            return self.add_workdays(moment, -count)
        cursor = moment
        remaining = count
        while remaining:
            cursor -= timedelta(days=1)
            if self.is_workday(cursor.date()):
                remaining -= 1
        return cursor

    def workdays_between(self, start: date, end: date, *, include_end: bool = True) -> int:
        if end < start:
            return -self.workdays_between(end, start, include_end=include_end)
        cursor = start
        total = 0
        while cursor <= end:
            if cursor != start and (include_end or cursor < end) and self.is_workday(cursor):
                total += 1
            cursor += timedelta(days=1)
        return total

    def list_days(self, start: date, end: date) -> list[CalendarDay]:
        return list(
            self.db.scalars(
                select(CalendarDay)
                .where(CalendarDay.day >= start, CalendarDay.day <= end)
                .order_by(CalendarDay.day)
            ).all()
        )

    def upsert_day(self, value: CalendarDayInput, *, updated_by: str | None = None) -> CalendarDay:
        item = self.db.get(CalendarDay, value.day)
        if item is None:
            item = CalendarDay(day=value.day, is_workday=value.is_workday)
            self.db.add(item)
        item.is_workday = value.is_workday
        item.holiday_name = value.holiday_name
        item.source = value.source
        item.version = value.version
        item.updated_by = updated_by
        self.db.flush()
        return item

    def import_days(self, values: Iterable[CalendarDayInput], *, updated_by: str | None = None) -> list[CalendarDay]:
        items: list[CalendarDay] = []
        seen: set[date] = set()
        for value in values:
            if value.day in seen:
                raise ValueError(f"duplicate calendar day: {value.day.isoformat()}")
            seen.add(value.day)
            items.append(self.upsert_day(value, updated_by=updated_by))
        return items

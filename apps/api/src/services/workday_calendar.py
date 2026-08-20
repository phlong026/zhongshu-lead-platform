from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.models_v12 import CalendarDay


CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True, slots=True)
class CalendarDayInput:
    day: date
    is_workday: bool
    holiday_name: str | None = None
    source: str = "MANUAL"
    version: int = 1


@dataclass(frozen=True, slots=True)
class CalendarDayMutation:
    item: CalendarDay
    created: bool
    changed: bool


@dataclass(frozen=True, slots=True)
class EffectiveCalendarDay:
    day: date
    is_workday: bool
    is_override: bool
    holiday_name: str | None
    source: str
    version: int | None
    updated_by: str | None
    updated_at: datetime | None


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
        aware = moment.tzinfo is not None and moment.utcoffset() is not None
        cursor = moment.astimezone(CHINA_TIMEZONE) if aware else moment
        remaining = count
        while remaining:
            cursor += timedelta(days=1)
            if self.is_workday(cursor.date()):
                remaining -= 1
        return cursor.astimezone(moment.tzinfo) if aware else cursor

    def subtract_workdays(self, moment: datetime, count: int) -> datetime:
        if count < 0:
            return self.add_workdays(moment, -count)
        aware = moment.tzinfo is not None and moment.utcoffset() is not None
        cursor = moment.astimezone(CHINA_TIMEZONE) if aware else moment
        remaining = count
        while remaining:
            cursor -= timedelta(days=1)
            if self.is_workday(cursor.date()):
                remaining -= 1
        return cursor.astimezone(moment.tzinfo) if aware else cursor

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

    def effective_day(self, day: date) -> EffectiveCalendarDay:
        item = self.get_day(day)
        if item is None:
            weekday = day.weekday() < 5
            return EffectiveCalendarDay(
                day=day,
                is_workday=weekday,
                is_override=False,
                holiday_name=None,
                source="DEFAULT_WEEKDAY" if weekday else "DEFAULT_WEEKEND",
                version=None,
                updated_by=None,
                updated_at=None,
            )
        return EffectiveCalendarDay(
            day=item.day,
            is_workday=bool(item.is_workday),
            is_override=True,
            holiday_name=item.holiday_name,
            source=item.source,
            version=item.version,
            updated_by=item.updated_by,
            updated_at=item.updated_at,
        )

    def list_effective_days(
        self,
        start: date,
        end: date,
    ) -> list[EffectiveCalendarDay]:
        explicit = {item.day: item for item in self.list_days(start, end)}
        result: list[EffectiveCalendarDay] = []
        cursor = start
        while cursor <= end:
            item = explicit.get(cursor)
            if item is None:
                weekday = cursor.weekday() < 5
                result.append(
                    EffectiveCalendarDay(
                        day=cursor,
                        is_workday=weekday,
                        is_override=False,
                        holiday_name=None,
                        source=(
                            "DEFAULT_WEEKDAY" if weekday else "DEFAULT_WEEKEND"
                        ),
                        version=None,
                        updated_by=None,
                        updated_at=None,
                    )
                )
            else:
                result.append(
                    EffectiveCalendarDay(
                        day=item.day,
                        is_workday=bool(item.is_workday),
                        is_override=True,
                        holiday_name=item.holiday_name,
                        source=item.source,
                        version=item.version,
                        updated_by=item.updated_by,
                        updated_at=item.updated_at,
                    )
                )
            cursor += timedelta(days=1)
        return result

    def upsert_day(
        self,
        value: CalendarDayInput,
        *,
        updated_by: str | None = None,
    ) -> CalendarDayMutation:
        item = self.db.get(CalendarDay, value.day)
        created = item is None
        if item is None:
            item = CalendarDay(
                day=value.day,
                is_workday=value.is_workday,
                holiday_name=value.holiday_name,
                source=value.source,
                version=value.version,
                updated_by=updated_by,
            )
            self.db.add(item)
            self.db.flush()
            return CalendarDayMutation(item=item, created=True, changed=True)
        changed = any(
            (
                bool(item.is_workday) != value.is_workday,
                item.holiday_name != value.holiday_name,
                item.source != value.source,
                item.version != value.version,
            )
        )
        if changed:
            item.is_workday = value.is_workday
            item.holiday_name = value.holiday_name
            item.source = value.source
            item.version = value.version
            item.updated_by = updated_by
            self.db.flush()
        return CalendarDayMutation(item=item, created=created, changed=changed)

    def import_days(
        self,
        values: Iterable[CalendarDayInput],
        *,
        updated_by: str | None = None,
    ) -> list[CalendarDayMutation]:
        inputs = list(values)
        seen: set[date] = set()
        for value in inputs:
            if value.day in seen:
                raise ValueError(f"duplicate calendar day: {value.day.isoformat()}")
            seen.add(value.day)
        return [
            self.upsert_day(value, updated_by=updated_by)
            for value in inputs
        ]

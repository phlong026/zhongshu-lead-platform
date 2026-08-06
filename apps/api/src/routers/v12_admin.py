from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..core.auth import require_permissions
from ..core.database import get_db
from ..core.errors import AppError
from ..core.responses import ok
from ..schemas.v12_calendar import CalendarDayBody, CalendarDayImportBody
from ..services.audit import write_audit
from ..services.workday_calendar import CalendarDayInput, WorkdayCalendarService

router = APIRouter(prefix="/admin/v1.2", tags=["admin-v1.2"])


def _serialize(item) -> dict:
    return {
        "day": item.day.isoformat(),
        "is_workday": item.is_workday,
        "holiday_name": item.holiday_name,
        "source": item.source,
        "version": item.version,
        "updated_by": item.updated_by,
        "updated_at": item.updated_at.isoformat(),
    }


@router.get("/calendar-days")
def list_calendar_days(
    request: Request,
    principal=Depends(require_permissions("*")),
    db: Session = Depends(get_db),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
):
    start = start or date.today()
    end = end or (start + timedelta(days=60))
    if end < start or (end - start).days > 366:
        raise AppError("INVALID_DATE_RANGE", "日期范围必须为 0 至 366 天", 422)
    items = WorkdayCalendarService(db).list_days(start, end)
    return ok(request, [_serialize(item) for item in items])


@router.put("/calendar-days/{day}")
def put_calendar_day(
    day: date,
    body: CalendarDayBody,
    request: Request,
    principal=Depends(require_permissions("*")),
    db: Session = Depends(get_db),
):
    service = WorkdayCalendarService(db)
    before_item = service.get_day(day)
    before = _serialize(before_item) if before_item else None
    item = service.upsert_day(
        CalendarDayInput(
            day=day,
            is_workday=body.is_workday,
            holiday_name=body.holiday_name,
            source=body.source,
            version=body.version,
        ),
        updated_by=principal.user_id,
    )
    write_audit(
        db,
        principal=principal,
        action="V12_CALENDAR_DAY_UPSERT",
        resource_type="calendar_day",
        resource_id=day.isoformat(),
        before=before,
        after=_serialize(item),
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, _serialize(item), "工作日历已保存")


@router.post("/calendar-days/import")
def import_calendar_days(
    body: CalendarDayImportBody,
    request: Request,
    principal=Depends(require_permissions("*")),
    db: Session = Depends(get_db),
):
    service = WorkdayCalendarService(db)
    try:
        items = service.import_days(
            [
                CalendarDayInput(
                    day=value.day,
                    is_workday=value.is_workday,
                    holiday_name=value.holiday_name,
                    source=value.source,
                    version=value.version,
                )
                for value in body.days
            ],
            updated_by=principal.user_id,
        )
    except ValueError as exc:
        raise AppError("DUPLICATE_CALENDAR_DAY", str(exc), 422) from exc
    ordered_days = sorted(item.day for item in items)
    write_audit(
        db,
        principal=principal,
        action="V12_CALENDAR_IMPORT",
        resource_type="calendar_day",
        resource_id=None,
        after={
            "count": len(items),
            "start": ordered_days[0].isoformat(),
            "end": ordered_days[-1].isoformat(),
        },
        request_id=request.state.request_id,
    )
    db.commit()
    return ok(request, {"count": len(items)}, "工作日历导入完成")

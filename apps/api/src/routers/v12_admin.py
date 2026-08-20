from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.auth import require_permissions
from ..core.database import get_db
from ..core.errors import AppError
from ..core.models import User
from ..core.responses import ok
from ..schemas.v12_calendar import CalendarDayBody, CalendarDayImportBody
from ..services.audit import write_audit
from ..services.workday_calendar import (
    CHINA_TIMEZONE,
    CalendarDayInput,
    EffectiveCalendarDay,
    WorkdayCalendarService,
)

router = APIRouter(prefix="/admin/v1.2", tags=["admin-v1.2"])


def _serialize(
    item: EffectiveCalendarDay,
    editor_names: dict[str, str] | None = None,
) -> dict:
    return {
        "day": item.day.isoformat(),
        "is_workday": item.is_workday,
        "is_override": item.is_override,
        "holiday_name": item.holiday_name,
        "source": item.source,
        "version": item.version,
        "updated_by": item.updated_by,
        "updated_by_name": (editor_names or {}).get(item.updated_by or ""),
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _editor_names(db: Session, items: list[EffectiveCalendarDay]) -> dict[str, str]:
    editor_ids = {item.updated_by for item in items if item.updated_by}
    if not editor_ids:
        return {}
    return dict(
        db.execute(
            select(User.id, User.display_name).where(User.id.in_(editor_ids))
        ).all()
    )


@router.get("/calendar-days")
def list_calendar_days(
    request: Request,
    principal=Depends(require_permissions("calendar.read")),
    db: Session = Depends(get_db),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
):
    start = start or datetime.now(CHINA_TIMEZONE).date()
    end = end or (start + timedelta(days=60))
    if end < start or (end - start).days > 366:
        raise AppError("INVALID_DATE_RANGE", "日期范围必须为 0 至 366 天", 422)
    items = WorkdayCalendarService(db).list_effective_days(start, end)
    editor_names = _editor_names(db, items)
    return ok(request, [_serialize(item, editor_names) for item in items])


@router.put("/calendar-days/{day}")
def put_calendar_day(
    day: date,
    body: CalendarDayBody,
    request: Request,
    principal=Depends(require_permissions("calendar.manage")),
    db: Session = Depends(get_db),
):
    service = WorkdayCalendarService(db)
    before = _serialize(service.effective_day(day))
    mutation = service.upsert_day(
        CalendarDayInput(
            day=day,
            is_workday=body.is_workday,
            holiday_name=body.holiday_name,
            source=body.source,
            version=body.version,
        ),
        updated_by=principal.user_id,
    )
    after_item = service.effective_day(day)
    after = _serialize(
        after_item,
        {principal.user_id: principal.display_name},
    )
    if mutation.changed:
        write_audit(
            db,
            principal=principal,
            action="V12_CALENDAR_DAY_UPSERT",
            resource_type="calendar_day",
            resource_id=day.isoformat(),
            before=before,
            after=after,
            request_id=request.state.request_id,
        )
        db.commit()
    return ok(
        request,
        {
            **after,
            "created": mutation.created,
            "changed": mutation.changed,
            "impact_scope": "FUTURE_CALCULATIONS_ONLY",
        },
        "工作日历已保存" if mutation.changed else "工作日历无变化",
    )


@router.post("/calendar-days/import")
def import_calendar_days(
    body: CalendarDayImportBody,
    request: Request,
    principal=Depends(require_permissions("calendar.import")),
    db: Session = Depends(get_db),
):
    service = WorkdayCalendarService(db)
    try:
        mutations = service.import_days(
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
    ordered_days = sorted(mutation.item.day for mutation in mutations)
    changed = [mutation for mutation in mutations if mutation.changed]
    changed_days = sorted(mutation.item.day for mutation in changed)
    created_count = sum(mutation.created for mutation in changed)
    updated_count = len(changed) - created_count
    result = {
        "count": len(mutations),
        "created_count": created_count,
        "updated_count": updated_count,
        "unchanged_count": len(mutations) - len(changed),
        "changed_count": len(changed),
        "start": ordered_days[0].isoformat(),
        "end": ordered_days[-1].isoformat(),
        "impact_start": changed_days[0].isoformat() if changed_days else None,
        "impact_end": changed_days[-1].isoformat() if changed_days else None,
        "impact_scope": "FUTURE_CALCULATIONS_ONLY",
    }
    if changed:
        write_audit(
            db,
            principal=principal,
            action="V12_CALENDAR_IMPORT",
            resource_type="calendar_day",
            resource_id=None,
            after={
                **result,
                "changed_days": [day.isoformat() for day in changed_days],
            },
            request_id=request.state.request_id,
        )
        db.commit()
    return ok(
        request,
        result,
        "工作日历导入完成" if changed else "工作日历无变化",
    )

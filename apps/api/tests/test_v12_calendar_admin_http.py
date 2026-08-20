from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from apps.api.src.core.models import AuditLog, User
from apps.api.src.core.models_v12 import CalendarDay


def _login(client, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    return token


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _data(response):
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["code"] == "OK"
    return payload["data"]


def _put_day(
    client,
    token: str,
    day: str,
    *,
    is_workday: bool,
    holiday_name: str,
    source: str = "MANUAL",
    version: int = 1,
):
    return client.put(
        f"/api/v1/admin/v1.2/calendar-days/{day}",
        headers=_bearer(token),
        json={
            "is_workday": is_workday,
            "holiday_name": holiday_name,
            "source": source,
            "version": version,
        },
    )


def test_calendar_permissions_separate_read_and_manage(api_client) -> None:
    client, _ = api_client
    operation = _login(client, "operation", "Operation123!")
    owner = _login(client, "owner", "Owner123!")
    telesales = _login(client, "telesales", "Telesales123!")

    assert client.get(
        "/api/v1/admin/v1.2/calendar-days?start=2026-08-01&end=2026-08-31",
        headers=_bearer(operation),
    ).status_code == 200
    assert _put_day(
        client,
        operation,
        "2026-08-08",
        is_workday=True,
        holiday_name="周末调休",
    ).status_code == 403
    assert _put_day(
        client,
        owner,
        "2026-08-08",
        is_workday=True,
        holiday_name="周末调休",
    ).status_code == 200
    assert client.get(
        "/api/v1/admin/v1.2/calendar-days?start=2026-08-01&end=2026-08-31",
        headers=_bearer(telesales),
    ).status_code == 403


def test_calendar_list_returns_effective_defaults_and_editor_name(api_client) -> None:
    client, _ = api_client
    admin = _login(client, "admin", "Admin123!")
    _data(
        _put_day(
            client,
            admin,
            "2026-08-08",
            is_workday=True,
            holiday_name="周六调休工作日",
        )
    )
    _data(
        _put_day(
            client,
            admin,
            "2026-08-10",
            is_workday=False,
            holiday_name="测试法定节假日",
            source="OFFICIAL",
        )
    )

    days = _data(
        client.get(
            "/api/v1/admin/v1.2/calendar-days?start=2026-08-08&end=2026-08-10",
            headers=_bearer(admin),
        )
    )

    assert [item["day"] for item in days] == [
        "2026-08-08",
        "2026-08-09",
        "2026-08-10",
    ]
    assert days[0]["is_workday"] is True
    assert days[0]["is_override"] is True
    assert days[0]["updated_by_name"] == "平台超级管理员"
    assert days[1]["is_workday"] is False
    assert days[1]["is_override"] is False
    assert days[1]["source"] == "DEFAULT_WEEKEND"
    assert days[2]["is_workday"] is False
    assert days[2]["source"] == "OFFICIAL"


def test_single_day_repeat_is_audited_only_when_data_changes(api_client) -> None:
    client, factory = api_client
    admin = _login(client, "admin", "Admin123!")

    first = _data(
        _put_day(
            client,
            admin,
            "2026-10-01",
            is_workday=False,
            holiday_name="国庆节",
            source="OFFICIAL",
        )
    )
    with factory() as db:
        first_updated_at = db.get(
            CalendarDay,
            date.fromisoformat(first["day"]),
        ).updated_at

    second = _data(
        _put_day(
            client,
            admin,
            "2026-10-01",
            is_workday=False,
            holiday_name="国庆节",
            source="OFFICIAL",
        )
    )

    assert first["created"] is True
    assert first["changed"] is True
    assert second["created"] is False
    assert second["changed"] is False
    with factory() as db:
        assert db.get(
            CalendarDay,
            date.fromisoformat(first["day"]),
        ).updated_at == first_updated_at
        assert db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == "V12_CALENDAR_DAY_UPSERT",
                AuditLog.resource_id == "2026-10-01",
            )
        ) == 1


def test_repeated_calendar_import_is_idempotent_and_reports_impact(api_client) -> None:
    client, factory = api_client
    owner = _login(client, "owner", "Owner123!")
    body = {
        "days": [
            {
                "day": "2026-10-01",
                "is_workday": False,
                "holiday_name": "国庆节",
                "source": "OFFICIAL",
                "version": 1,
            },
            {
                "day": "2026-10-10",
                "is_workday": True,
                "holiday_name": "国庆调休工作日",
                "source": "OFFICIAL",
                "version": 1,
            },
        ]
    }

    first = _data(
        client.post(
            "/api/v1/admin/v1.2/calendar-days/import",
            headers=_bearer(owner),
            json=body,
        )
    )
    second = _data(
        client.post(
            "/api/v1/admin/v1.2/calendar-days/import",
            headers=_bearer(owner),
            json=body,
        )
    )

    assert first == {
        "count": 2,
        "created_count": 2,
        "updated_count": 0,
        "unchanged_count": 0,
        "changed_count": 2,
        "start": "2026-10-01",
        "end": "2026-10-10",
        "impact_start": "2026-10-01",
        "impact_end": "2026-10-10",
        "impact_scope": "FUTURE_CALCULATIONS_ONLY",
    }
    assert second["created_count"] == 0
    assert second["updated_count"] == 0
    assert second["unchanged_count"] == 2
    assert second["changed_count"] == 0
    assert second["impact_start"] is None
    assert second["impact_end"] is None
    with factory() as db:
        owner_user = db.scalar(select(User).where(User.username == "owner"))
        assert owner_user is not None
        assert db.get(
            CalendarDay,
            date(2026, 10, 1),
        ).updated_by == owner_user.id
        assert db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == "V12_CALENDAR_IMPORT"
            )
        ) == 1

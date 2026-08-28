from __future__ import annotations

from apps.api.src.main import app


def test_company_delete_route_is_not_registered() -> None:
    delete_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/companies/{company_id}"
        and "DELETE" in getattr(route, "methods", set())
    ]

    assert delete_routes == []

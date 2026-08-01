from __future__ import annotations

from typing import Any

from fastapi import Request


def ok(request: Request, data: Any = None, message: str = "ok") -> dict[str, Any]:
    return {"code": "OK", "message": message, "data": data, "request_id": getattr(request.state, "request_id", None)}


def page(items: list[Any], total: int, page_no: int, page_size: int) -> dict[str, Any]:
    return {"items": items, "total": total, "page": page_no, "page_size": page_size}

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse


ASGIApp = Callable[[dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]], Awaitable[None]]


class InFlightLimitMiddleware:
    """Queue excess HTTP requests before they can reserve worker or DB capacity."""

    def __init__(self, app: ASGIApp, limit: int, queue_timeout_seconds: float) -> None:
        if limit <= 0 or queue_timeout_seconds <= 0:
            raise ValueError("in-flight limit and queue timeout must be positive")
        self.app = app
        self._semaphore = asyncio.Semaphore(limit)
        self._queue_timeout_seconds = queue_timeout_seconds

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self._queue_timeout_seconds,
            )
        except TimeoutError:
            response = JSONResponse(
                status_code=503,
                content={
                    "code": "SERVER_BUSY",
                    "message": "服务器繁忙，请稍后重试",
                    "data": None,
                    "details": {"retry_after_seconds": 1},
                    "request_id": scope.get("state", {}).get("request_id"),
                },
                headers={"Retry-After": "1", "Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            self._semaphore.release()

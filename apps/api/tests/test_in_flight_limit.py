from __future__ import annotations

import asyncio

from apps.api.src.core.in_flight import InFlightLimitMiddleware


def test_http_requests_queue_before_the_wrapped_application() -> None:
    active = 0
    peak = 0

    async def wrapped(_scope, _receive, _send) -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1

    async def exercise() -> None:
        middleware = InFlightLimitMiddleware(wrapped, limit=2, queue_timeout_seconds=1)

        async def receive():
            return {"type": "http.disconnect"}

        async def send(_message) -> None:
            return None

        await asyncio.gather(
            *(middleware({"type": "http", "path": "/api/v1/test"}, receive, send) for _ in range(8))
        )

    asyncio.run(exercise())
    assert peak == 2


def test_excess_request_fails_fast_when_the_queue_timeout_expires() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    wrapped_calls = 0
    messages: list[dict] = []

    async def wrapped(_scope, _receive, _send) -> None:
        nonlocal wrapped_calls
        wrapped_calls += 1
        entered.set()
        await release.wait()

    async def exercise() -> None:
        middleware = InFlightLimitMiddleware(wrapped, limit=1, queue_timeout_seconds=0.01)

        async def receive():
            return {"type": "http.disconnect"}

        async def send(message) -> None:
            messages.append(message)

        first = asyncio.create_task(middleware({"type": "http", "path": "/slow"}, receive, send))
        await entered.wait()
        await middleware({"type": "http", "path": "/queued"}, receive, send)
        release.set()
        await first

    asyncio.run(exercise())

    assert wrapped_calls == 1
    response_start = next(message for message in messages if message["type"] == "http.response.start")
    assert response_start["status"] == 503
    assert (b"retry-after", b"1") in response_start["headers"]

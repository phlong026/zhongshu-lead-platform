from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import Event, Lock
from typing import Any, Callable

from ..core.errors import AppError


@dataclass(frozen=True, slots=True)
class _FailureSnapshot:
    is_app_error: bool
    error_type: str
    message: str
    code: str | None = None
    status_code: int | None = None
    details: Any = None

    @classmethod
    def from_exception(cls, exc: Exception) -> "_FailureSnapshot":
        if isinstance(exc, AppError):
            return cls(
                is_app_error=True,
                error_type=type(exc).__name__,
                message=exc.message,
                code=exc.code,
                status_code=exc.status_code,
                details=deepcopy(exc.details),
            )
        return cls(
            is_app_error=False,
            error_type=type(exc).__name__,
            message=str(exc) or type(exc).__name__,
        )

    def raise_follower_copy(self) -> None:
        if self.is_app_error:
            raise AppError(
                self.code or "CLAIM_FAILED",
                self.message,
                int(self.status_code or 400),
                deepcopy(self.details),
            )
        raise AppError(
            "CLAIM_TRANSIENT_FAILURE",
            "领取请求暂时失败，请稍后重试",
            503,
            {"failure_type": self.error_type},
        )


@dataclass
class _FlightEntry:
    event: Event = field(default_factory=Event)
    users: int = 0
    result: Any = None
    failure: _FailureSnapshot | None = None


_guard = Lock()
_flights: dict[str, _FlightEntry] = {}


def _join_or_create(key: str) -> tuple[_FlightEntry, bool]:
    with _guard:
        entry = _flights.get(key)
        if entry is None:
            entry = _FlightEntry(users=1)
            _flights[key] = entry
            return entry, True
        entry.users += 1
        return entry, False


def _release(key: str, entry: _FlightEntry) -> None:
    with _guard:
        entry.users -= 1
        if entry.users <= 0 and _flights.get(key) is entry:
            _flights.pop(key, None)


def run_claim_singleflight(
    claim_key: str,
    execute: Callable[[], Any],
    *,
    wait_timeout_seconds: float = 2.0,
    before_wait: Callable[[], None] | None = None,
) -> tuple[Any, bool]:
    """Collapse same-company/same-assignment requests inside one API worker.

    This is an optimization, not the transaction authority. The leader executes
    the existing PostgreSQL-backed claim service. Followers release any
    read-only transaction before waiting and receive a deep-copied plain
    response. Multiple workers/processes still converge through database row
    locks and the claim ledger idempotency key.
    """

    key = claim_key.strip()
    if not key:
        return execute(), False

    entry, leader = _join_or_create(key)
    if leader:
        try:
            result = execute()
            with _guard:
                entry.result = deepcopy(result)
                entry.event.set()
            return result, False
        except Exception as exc:
            with _guard:
                entry.failure = _FailureSnapshot.from_exception(exc)
                entry.event.set()
            raise
        finally:
            _release(key, entry)

    try:
        if before_wait is not None:
            before_wait()
        if not entry.event.wait(timeout=max(0.01, float(wait_timeout_seconds))):
            raise AppError(
                "CLAIM_IN_PROGRESS_TIMEOUT",
                "领取请求正在处理中，请稍后重试",
                503,
            )
        with _guard:
            result = deepcopy(entry.result)
            failure = entry.failure
        if failure is not None:
            failure.raise_follower_copy()
        if result is None:
            raise AppError(
                "CLAIM_TRANSIENT_FAILURE",
                "领取请求暂时失败，请稍后重试",
                503,
                {"failure_type": "missing_singleflight_result"},
            )
        return result, True
    finally:
        _release(key, entry)

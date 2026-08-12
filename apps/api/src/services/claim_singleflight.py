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


def _release(key: str, entry: _FlightEntry) -> None:
    with _guard:
        entry.users -= 1
        if entry.users <= 0 and _flights.get(key) is entry:
            _flights.pop(key, None)


def _join_or_create(key: str) -> tuple[_FlightEntry, bool]:
    with _guard:
        entry = _flights.get(key)
        if entry is None:
            entry = _FlightEntry(users=1)
            _flights[key] = entry
            return entry, True
        entry.users += 1
        return entry, False


def run_claim_singleflight(
    assignment_id: str,
    execute: Callable[[], Any],
    *,
    wait_timeout_seconds: float = 2.0,
) -> tuple[Any, bool]:
    """Collapse concurrent claims for one assignment inside an API worker.

    One leader executes the authoritative transaction and followers reuse its
    successful result. Deterministic business failures are shared with followers.
    A transient leader failure is also shared as retryable 503 and the failed
    generation stays registered until every caller in that burst has observed it;
    no follower independently re-enters the database. A later, separate request may
    start a fresh flight after the failed generation has drained.
    """

    key = assignment_id.strip()
    if not key:
        return execute(), False

    entry, leader = _join_or_create(key)
    if leader:
        try:
            result = execute()
            with _guard:
                entry.result = deepcopy(result)
                entry.failure = None
                entry.event.set()
            return result, False
        except Exception as exc:
            with _guard:
                entry.failure = _FailureSnapshot.from_exception(exc)
                entry.event.set()
            raise
        finally:
            _release(key, entry)

    completed = entry.event.wait(timeout=max(0.01, float(wait_timeout_seconds)))
    if not completed:
        _release(key, entry)
        raise AppError(
            "CLAIM_IN_PROGRESS_TIMEOUT",
            "领取请求正在处理中，请稍后重试",
            503,
        )

    with _guard:
        result = deepcopy(entry.result)
        failure = entry.failure
    _release(key, entry)
    if failure is None and result is not None:
        return result, True
    if failure is None:
        raise RuntimeError("claim singleflight completed without a result or failure")
    failure.raise_follower_copy()

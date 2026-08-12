from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import Event, Lock, Timer
from time import monotonic
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
    failure_expires_at: float | None = None


_guard = Lock()
_flights: dict[str, _FlightEntry] = {}


def _failure_is_retained(entry: _FlightEntry, now: float | None = None) -> bool:
    expires_at = entry.failure_expires_at
    return (
        entry.failure is not None
        and expires_at is not None
        and (now if now is not None else monotonic()) < expires_at
    )


def _expire_failed_entry(key: str, entry: _FlightEntry) -> None:
    with _guard:
        if (
            _flights.get(key) is entry
            and entry.users <= 0
            and entry.failure is not None
            and not _failure_is_retained(entry)
        ):
            _flights.pop(key, None)


def _release(key: str, entry: _FlightEntry) -> None:
    with _guard:
        entry.users -= 1
        if entry.users <= 0 and _flights.get(key) is entry and not _failure_is_retained(entry):
            _flights.pop(key, None)


def _join_or_create(key: str) -> tuple[_FlightEntry, bool]:
    with _guard:
        entry = _flights.get(key)
        if entry is not None and entry.users <= 0 and entry.failure is not None and not _failure_is_retained(entry):
            _flights.pop(key, None)
            entry = None
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
    failure_retention_seconds: float = 5.0,
    before_wait: Callable[[], None] | None = None,
) -> tuple[Any, bool]:
    """Collapse concurrent claims for one assignment inside an API worker.

    One leader executes the authoritative transaction and followers reuse its
    successful result. Business/transient failures are shared without new database
    work. Failed flights remain addressable for a short grace window after joined
    callers drain, so executor/in-flight waves from the same HTTP burst do not each
    elect a new leader. A daemon timer removes the retained failure even if no later
    request touches the key.

    `before_wait` is invoked for followers only. The HTTP path uses it to roll back
    the read-only authentication transaction so coalesced waiters return their
    PostgreSQL connection to the pool instead of consuming the release connection
    budget while the leader performs the business transaction.
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
                entry.failure_expires_at = None
                entry.event.set()
            return result, False
        except Exception as exc:
            retention = max(0.05, float(failure_retention_seconds))
            with _guard:
                entry.failure = _FailureSnapshot.from_exception(exc)
                entry.failure_expires_at = monotonic() + retention
                entry.event.set()
            timer = Timer(retention, _expire_failed_entry, args=(key, entry))
            timer.daemon = True
            timer.start()
            raise
        finally:
            _release(key, entry)

    if before_wait is not None:
        try:
            before_wait()
        except Exception:
            _release(key, entry)
            raise

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

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

    def raise_copy(self) -> None:
        if self.is_app_error:
            raise AppError(
                self.code or "CLAIM_FAILED",
                self.message,
                int(self.status_code or 400),
                deepcopy(self.details),
            )
        raise RuntimeError(f"coalesced claim leader failed: {self.error_type}: {self.message}")


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
    transient_re_elections: int = 1,
) -> tuple[Any, bool]:
    """Collapse concurrent claims for one assignment inside an API worker.

    One leader executes the authoritative transaction. Followers reuse the leader
    result. Deterministic AppError failures are replayed to followers without new
    database work. For a non-business transient exception, at most one replacement
    leader is elected; the rest remain coalesced. A stuck leader causes followers to
    return a retryable 503 instead of creating a database thundering herd.
    """

    key = assignment_id.strip()
    if not key:
        return execute(), False

    remaining_re_elections = max(0, int(transient_re_elections))
    while True:
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
                failure = _FailureSnapshot.from_exception(exc)
                with _guard:
                    entry.failure = failure
                    entry.event.set()
                    # Close this failed generation immediately. Existing followers
                    # still hold `entry`; a transient retry can elect exactly one
                    # replacement leader in a fresh generation.
                    if _flights.get(key) is entry:
                        _flights.pop(key, None)
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
        if failure.is_app_error:
            failure.raise_copy()
        if remaining_re_elections <= 0:
            failure.raise_copy()
        remaining_re_elections -= 1
        # Rejoin a fresh generation. The first follower becomes replacement leader;
        # all remaining followers join it instead of calling execute independently.

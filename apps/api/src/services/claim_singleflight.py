from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import Event, Lock
from typing import Any, Callable


@dataclass
class _FlightEntry:
    event: Event = field(default_factory=Event)
    users: int = 0
    result: Any = None
    failed: bool = False


_guard = Lock()
_flights: dict[str, _FlightEntry] = {}


def _release(key: str, entry: _FlightEntry) -> None:
    with _guard:
        entry.users -= 1
        if entry.users <= 0 and _flights.get(key) is entry:
            _flights.pop(key, None)


def run_claim_singleflight(
    assignment_id: str,
    execute: Callable[[], Any],
    *,
    wait_timeout_seconds: float = 10.0,
) -> tuple[Any, bool]:
    """Collapse concurrent claims for one assignment inside an API worker.

    The first caller executes the authoritative transaction. Followers wait for
    the committed response snapshot instead of entering the same row-lock queue.
    The boolean result is true only when a follower reused the leader result.
    """

    key = assignment_id.strip()
    if not key:
        return execute(), False

    with _guard:
        entry = _flights.get(key)
        if entry is None:
            entry = _FlightEntry(users=1)
            _flights[key] = entry
            leader = True
        else:
            entry.users += 1
            leader = False

    if leader:
        try:
            result = execute()
            with _guard:
                entry.result = deepcopy(result)
                entry.failed = False
                entry.event.set()
            return result, False
        except Exception:
            with _guard:
                entry.failed = True
                entry.event.set()
            raise
        finally:
            _release(key, entry)

    completed = entry.event.wait(timeout=max(0.01, float(wait_timeout_seconds)))
    if completed:
        with _guard:
            failed = entry.failed
            result = deepcopy(entry.result)
        _release(key, entry)
        if not failed and result is not None:
            return result, True
    else:
        _release(key, entry)

    # A failed or timed-out leader is never treated as a successful claim.
    # Fall back to the database path, whose transaction/idempotency rules remain
    # the final correctness boundary.
    return execute(), False

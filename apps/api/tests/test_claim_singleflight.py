from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import time

from apps.api.src.services.claim_singleflight import run_claim_singleflight


def test_singleflight_collapses_same_assignment_burst() -> None:
    callers = 20
    barrier = Barrier(callers)
    lock = Lock()
    executions = 0

    def execute():
        nonlocal executions
        with lock:
            executions += 1
        time.sleep(0.05)
        return {"assignment_id": "assignment-1", "idempotent": False}

    def worker():
        barrier.wait()
        return run_claim_singleflight("assignment-1", execute)

    with ThreadPoolExecutor(max_workers=callers) as pool:
        results = list(pool.map(lambda _: worker(), range(callers)))

    assert executions == 1
    assert sum(1 for _, coalesced in results if coalesced) == callers - 1
    assert all(payload["assignment_id"] == "assignment-1" for payload, _ in results)


def test_singleflight_does_not_mix_different_assignments() -> None:
    barrier = Barrier(2)
    lock = Lock()
    executions: list[str] = []

    def worker(key: str):
        barrier.wait()

        def execute():
            with lock:
                executions.append(key)
            return {"assignment_id": key}

        return run_claim_singleflight(key, execute)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, ["assignment-a", "assignment-b"]))

    assert sorted(executions) == ["assignment-a", "assignment-b"]
    assert all(coalesced is False for _, coalesced in results)


def test_singleflight_failed_leader_is_not_reused_as_success() -> None:
    calls = 0

    def execute():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("leader failed")
        return {"ok": True}

    try:
        run_claim_singleflight("assignment-fail", execute)
    except RuntimeError:
        pass

    payload, coalesced = run_claim_singleflight("assignment-fail", execute)
    assert payload == {"ok": True}
    assert coalesced is False

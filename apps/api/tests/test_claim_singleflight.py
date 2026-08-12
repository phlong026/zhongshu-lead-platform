from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import time

from apps.api.src.core.errors import AppError
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


def test_transient_failure_elects_only_one_replacement_leader() -> None:
    callers = 20
    barrier = Barrier(callers)
    lock = Lock()
    executions = 0

    def execute():
        nonlocal executions
        with lock:
            executions += 1
            call_number = executions
        time.sleep(0.08)
        if call_number == 1:
            raise RuntimeError("transient database failure")
        return {"assignment_id": "assignment-retry", "idempotent": False}

    def worker():
        barrier.wait()
        return run_claim_singleflight("assignment-retry", execute)

    successes = []
    failures = []
    with ThreadPoolExecutor(max_workers=callers) as pool:
        futures = [pool.submit(worker) for _ in range(callers)]
        for future in futures:
            try:
                successes.append(future.result())
            except RuntimeError as exc:
                failures.append(exc)

    assert executions == 2
    assert len(failures) == 1
    assert len(successes) == callers - 1
    assert all(payload["assignment_id"] == "assignment-retry" for payload, _ in successes)


def test_app_error_is_shared_without_database_reexecution() -> None:
    callers = 10
    barrier = Barrier(callers)
    lock = Lock()
    executions = 0

    def execute():
        nonlocal executions
        with lock:
            executions += 1
        time.sleep(0.08)
        raise AppError("POINTS_INSUFFICIENT", "积分不足", 409, {"balance": 0})

    def worker():
        barrier.wait()
        return run_claim_singleflight("assignment-business-error", execute)

    errors: list[AppError] = []
    with ThreadPoolExecutor(max_workers=callers) as pool:
        futures = [pool.submit(worker) for _ in range(callers)]
        for future in futures:
            try:
                future.result()
            except AppError as exc:
                errors.append(exc)

    assert executions == 1
    assert len(errors) == callers
    assert all(error.code == "POINTS_INSUFFICIENT" for error in errors)
    assert all(error.status_code == 409 for error in errors)


def test_timed_out_follower_returns_retryable_error_without_new_leader() -> None:
    barrier = Barrier(2)
    lock = Lock()
    executions = 0

    def execute():
        nonlocal executions
        with lock:
            executions += 1
        time.sleep(0.15)
        return {"ok": True}

    def worker():
        barrier.wait()
        return run_claim_singleflight(
            "assignment-timeout",
            execute,
            wait_timeout_seconds=0.02,
        )

    successes = []
    errors: list[AppError] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        for future in futures:
            try:
                successes.append(future.result())
            except AppError as exc:
                errors.append(exc)

    assert executions == 1
    assert len(successes) == 1
    assert len(errors) == 1
    assert errors[0].code == "CLAIM_IN_PROGRESS_TIMEOUT"
    assert errors[0].status_code == 503

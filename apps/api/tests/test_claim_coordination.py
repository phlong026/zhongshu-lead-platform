from __future__ import annotations

from types import SimpleNamespace

import apps.api.src.services.claim_coordination as coordination
from apps.api.src.services.claim_coordination import claim_advisory_lock_key


class _FakePostgresSession:
    def __init__(self) -> None:
        self.expire_calls = 0

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def expire_all(self) -> None:
        self.expire_calls += 1


def _pending_probe(company_id: str = "company-1"):
    return SimpleNamespace(assignment=SimpleNamespace(company_id=company_id))


def test_claim_advisory_lock_key_is_stable_signed_bigint() -> None:
    first = claim_advisory_lock_key("11111111-2222-3333-4444-555555555555")
    second = claim_advisory_lock_key("11111111-2222-3333-4444-555555555555")
    other = claim_advisory_lock_key("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    assert first == second
    assert first != other
    assert -(1 << 63) <= first < (1 << 63)
    assert -(1 << 63) <= other < (1 << 63)


def test_existing_claim_result_returns_before_postgres_lock(monkeypatch) -> None:
    db = _FakePostgresSession()
    existing = object()
    monkeypatch.setattr(coordination, "_claim_probe", lambda *args, **kwargs: _pending_probe())
    monkeypatch.setattr(coordination, "_existing_claim_result", lambda **kwargs: existing)
    monkeypatch.setattr(
        coordination,
        "_try_postgres_advisory_lock",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("lock must not run")),
    )

    result = coordination.claim_assignment_coordinated(
        db,
        assignment_id="assignment-1",
        company_id="company-1",
        claimed_by="user-1",
    )

    assert result is existing
    assert db.expire_calls == 0


def test_postgres_leader_uses_advisory_lock_then_authoritative_claim(monkeypatch) -> None:
    db = _FakePostgresSession()
    sentinel = object()
    monkeypatch.setattr(coordination, "_claim_probe", lambda *args, **kwargs: _pending_probe())
    monkeypatch.setattr(coordination, "_existing_claim_result", lambda **kwargs: None)
    monkeypatch.setattr(coordination, "_try_postgres_advisory_lock", lambda *args, **kwargs: True)
    monkeypatch.setattr(coordination, "claim_assignment_fast", lambda *args, **kwargs: sentinel)

    result = coordination.claim_assignment_coordinated(
        db,
        assignment_id="assignment-1",
        company_id="company-1",
        claimed_by="user-1",
    )

    assert result is sentinel
    assert db.expire_calls == 1


def test_postgres_follower_observes_committed_claim_without_waiting_row_lock(monkeypatch) -> None:
    db = _FakePostgresSession()
    committed = object()
    existing_results = iter((None, committed))
    probe_calls = 0

    def probe(*args, **kwargs):
        nonlocal probe_calls
        probe_calls += 1
        return _pending_probe()

    monkeypatch.setattr(coordination, "_claim_probe", probe)
    monkeypatch.setattr(coordination, "_existing_claim_result", lambda **kwargs: next(existing_results))
    monkeypatch.setattr(coordination, "_try_postgres_advisory_lock", lambda *args, **kwargs: False)
    monkeypatch.setattr(coordination, "_POLL_DELAYS_SECONDS", (0.0,))
    monkeypatch.setattr(coordination.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        coordination,
        "_wait_for_postgres_advisory_lock",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("blocking advisory wait must not run")),
    )
    monkeypatch.setattr(
        coordination,
        "claim_assignment_fast",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("authoritative claim must not rerun")),
    )

    result = coordination.claim_assignment_coordinated(
        db,
        assignment_id="assignment-1",
        company_id="company-1",
        claimed_by="user-1",
    )

    assert result is committed
    assert probe_calls == 2
    assert db.expire_calls == 0


def test_postgres_follower_budget_falls_back_to_one_advisory_wait(monkeypatch) -> None:
    db = _FakePostgresSession()
    sentinel = object()
    waits = 0

    def wait_for_lock(*args, **kwargs):
        nonlocal waits
        waits += 1

    monkeypatch.setattr(coordination, "_claim_probe", lambda *args, **kwargs: _pending_probe())
    monkeypatch.setattr(coordination, "_existing_claim_result", lambda **kwargs: None)
    monkeypatch.setattr(coordination, "_try_postgres_advisory_lock", lambda *args, **kwargs: False)
    monkeypatch.setattr(coordination, "_POLL_DELAYS_SECONDS", ())
    monkeypatch.setattr(coordination, "_wait_for_postgres_advisory_lock", wait_for_lock)
    monkeypatch.setattr(coordination, "claim_assignment_fast", lambda *args, **kwargs: sentinel)

    result = coordination.claim_assignment_coordinated(
        db,
        assignment_id="assignment-1",
        company_id="company-1",
        claimed_by="user-1",
    )

    assert result is sentinel
    assert waits == 1
    assert db.expire_calls == 1

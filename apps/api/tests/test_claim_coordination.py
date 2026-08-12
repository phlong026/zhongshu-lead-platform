from __future__ import annotations

from apps.api.src.services.claim_coordination import claim_advisory_lock_key


def test_claim_advisory_lock_key_is_stable_signed_bigint() -> None:
    first = claim_advisory_lock_key("11111111-2222-3333-4444-555555555555")
    second = claim_advisory_lock_key("11111111-2222-3333-4444-555555555555")
    other = claim_advisory_lock_key("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    assert first == second
    assert first != other
    assert -(1 << 63) <= first < (1 << 63)
    assert -(1 << 63) <= other < (1 << 63)

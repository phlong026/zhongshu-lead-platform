from __future__ import annotations

import pytest

from apps.api.src.core.state_machine_v12 import (
    InvalidStateTransition,
    assert_lead_transition,
    assert_return_transition,
    assert_reward_transition,
    map_legacy_lead_status,
    map_legacy_return_status,
)
from apps.api.src.core.v12_enums import LeadV12Status, ReturnV12Status, RewardStatus


def test_normal_lead_can_skip_pre_verification_and_enter_dispatch_pool() -> None:
    assert_lead_transition(LeadV12Status.DRAFT, LeadV12Status.READY_DISPATCH)


def test_supplier_lead_review_flow_is_supported() -> None:
    assert_lead_transition(LeadV12Status.DRAFT, LeadV12Status.PENDING_REVIEW)
    assert_lead_transition(LeadV12Status.PENDING_REVIEW, LeadV12Status.READY_DISPATCH)


def test_supplier_can_wait_in_public_pool_until_receiver_coverage_exists() -> None:
    assert_lead_transition(LeadV12Status.DRAFT, LeadV12Status.PUBLIC_POOL)
    assert_lead_transition(LeadV12Status.PENDING_REVIEW, LeadV12Status.PUBLIC_POOL)
    assert_lead_transition(
        LeadV12Status.PENDING_OPERATION_DISPOSITION,
        LeadV12Status.PUBLIC_POOL,
    )
    assert_lead_transition(LeadV12Status.PUBLIC_POOL, LeadV12Status.READY_DISPATCH)


def test_invalid_lead_transition_is_blocked() -> None:
    with pytest.raises(InvalidStateTransition):
        assert_lead_transition(LeadV12Status.DRAFT, LeadV12Status.CLAIMED)


def test_return_requires_post_submission_verification() -> None:
    assert_return_transition(ReturnV12Status.SUBMITTED, ReturnV12Status.VERIFYING)
    assert_return_transition(ReturnV12Status.VERIFYING, ReturnV12Status.REVIEWING)
    with pytest.raises(InvalidStateTransition):
        assert_return_transition(ReturnV12Status.SUBMITTED, ReturnV12Status.APPROVED)


def test_reward_reversal_is_only_available_after_settlement() -> None:
    assert_reward_transition(RewardStatus.SETTLED, RewardStatus.REVERSED)
    with pytest.raises(InvalidStateTransition):
        assert_reward_transition(RewardStatus.OBSERVING, RewardStatus.REVERSED)


def test_legacy_status_mapping_is_read_only_compatible() -> None:
    assert map_legacy_lead_status("QUALIFIED") is LeadV12Status.READY_DISPATCH
    assert map_legacy_lead_status("RETURNED") is LeadV12Status.READY_DISPATCH
    assert map_legacy_return_status("PENDING") is ReturnV12Status.SUBMITTED
    assert map_legacy_return_status("NEED_MORE") is ReturnV12Status.NEED_MORE_EVIDENCE

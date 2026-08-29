from __future__ import annotations

from ..core.errors import AppError
from ..core.models import Lead


CORRECTION_REVIEW_REASON = "CORRECTION_REVIEW_REQUIRED"


def lead_requires_correction_review(lead: Lead | None) -> bool:
    return bool(lead and lead.pending_reason == CORRECTION_REVIEW_REASON)


def require_correction_review_resolved(lead: Lead | None) -> None:
    if lead_requires_correction_review(lead):
        raise AppError(
            "LEAD_CORRECTION_REVIEW_REQUIRED",
            "客资更正后需运营先处理接收资格异常",
            409,
        )


def store_lead_correction_issues(
    lead: Lead,
    issues: list[str],
    *,
    require_action: bool = True,
) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(issues))
    payload = dict(lead.raw_payload or {})
    if normalized:
        payload["correction_issues"] = list(normalized)
        if require_action:
            lead.pending_reason = CORRECTION_REVIEW_REASON
        elif lead.pending_reason == CORRECTION_REVIEW_REASON:
            lead.pending_reason = None
    else:
        payload.pop("correction_issues", None)
        if lead.pending_reason == CORRECTION_REVIEW_REASON:
            lead.pending_reason = None
    lead.raw_payload = payload
    return normalized

from __future__ import annotations

# A person has one business responsibility at a time. Keeping this contract in
# core avoids each router inventing its own view of the active role set.
ACTIVE_BUSINESS_ROLE_CODES = frozenset(
    {
        "SUPER_ADMIN",
        "OPERATION",
        "TELESALES",
        "FRANCHISE_OWNER",
        "FRANCHISE_EMPLOYEE",
    }
)

LEGACY_ROLE_CODES = frozenset(
    {
        "OWNER",
        "LEAD_ENTRY",
        "FINANCE",
        "RETURN_REVIEWER",
    }
)


def has_exactly_one_active_business_role(role_codes: set[str] | frozenset[str] | list[str]) -> bool:
    return len(role_codes) == 1 and next(iter(role_codes)) in ACTIVE_BUSINESS_ROLE_CODES

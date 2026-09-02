from __future__ import annotations

from sqlalchemy import func, select

from apps.api.src.core.models import (
    Assignment,
    Company,
    Lead,
    PointsLedger,
    User,
    VerificationTemplate,
)
from apps.api.src.services.bootstrap import seed_demo


def test_demo_seed_is_idempotent(db):
    first = seed_demo(db)
    db.commit()
    counts_first = {
        "users": db.scalar(select(func.count(User.id))),
        "companies": db.scalar(select(func.count(Company.id))),
        "leads": db.scalar(select(func.count(Lead.id))),
        "assignments": db.scalar(select(func.count(Assignment.id))),
        "ledgers": db.scalar(select(func.count(PointsLedger.id))),
    }
    second = seed_demo(db)
    db.commit()
    counts_second = {
        "users": db.scalar(select(func.count(User.id))),
        "companies": db.scalar(select(func.count(Company.id))),
        "leads": db.scalar(select(func.count(Lead.id))),
        "assignments": db.scalar(select(func.count(Assignment.id))),
        "ledgers": db.scalar(select(func.count(PointsLedger.id))),
    }
    assert counts_first == counts_second
    assert first["company_id"] == second["company_id"]
    assert counts_first["leads"] >= 5
    assert counts_first["assignments"] == 2


def test_demo_seed_publishes_pre_dispatch_template(db):
    seed_demo(db)
    db.commit()

    template = db.scalar(
        select(VerificationTemplate).where(
            VerificationTemplate.code == "PRE_DISPATCH",
            VerificationTemplate.status == "PUBLISHED",
        )
    )

    assert template is not None
    assert template.name == "前置电销核验模板"
    assert template.schema_json == {"fields": []}

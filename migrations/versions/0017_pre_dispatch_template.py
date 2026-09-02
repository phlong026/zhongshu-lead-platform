"""Publish the default V1.2 pre-dispatch verification template.

Revision ID: 0017_pre_dispatch_template
Revises: 0016_lead_test_flag
"""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


revision = "0017_pre_dispatch_template"
down_revision = "0016_lead_test_flag"
branch_labels = None
depends_on = None


TEMPLATE_ID = "1f7b6405-9e0f-4ec7-a073-1dbd02b46137"
TEMPLATE_CODE = "PRE_DISPATCH"


def _table(name: str) -> sa.Table:
    return sa.Table(name, sa.MetaData(), autoload_with=op.get_bind())


def upgrade() -> None:
    templates = _table("verification_templates")
    connection = op.get_bind()
    published_count = connection.execute(
        sa.select(sa.func.count()).select_from(templates).where(
            templates.c.code == TEMPLATE_CODE,
            templates.c.status == "PUBLISHED",
        )
    ).scalar_one()
    if published_count:
        return

    latest_version = connection.execute(
        sa.select(sa.func.max(templates.c.version)).where(
            templates.c.code == TEMPLATE_CODE
        )
    ).scalar_one()
    now = datetime.now(timezone.utc)
    connection.execute(
        templates.insert().values(
            id=TEMPLATE_ID,
            code=TEMPLATE_CODE,
            name="前置电销核验模板",
            version=int(latest_version or 0) + 1,
            schema_json={"fields": []},
            status="PUBLISHED",
            effective_at=now,
            created_at=now,
            updated_at=now,
        )
    )


def downgrade() -> None:
    templates = _table("verification_templates")
    tasks = _table("verification_tasks")
    connection = op.get_bind()
    seeded_id = connection.execute(
        sa.select(templates.c.id).where(templates.c.id == TEMPLATE_ID)
    ).scalar_one_or_none()
    if seeded_id is None:
        return

    referenced_tasks = connection.execute(
        sa.select(sa.func.count()).select_from(tasks).where(
            tasks.c.template_id == TEMPLATE_ID
        )
    ).scalar_one()
    if referenced_tasks:
        raise RuntimeError(
            "pre-dispatch verification tasks reference the seeded template; "
            "complete or migrate those tasks before downgrade"
        )
    connection.execute(templates.delete().where(templates.c.id == TEMPLATE_ID))

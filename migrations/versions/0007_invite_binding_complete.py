"""Add invitation confirmation, snapshot, matching, and delivery audit tables.

Revision ID: 0007_invite_binding
Revises: 0006_capability_review_note
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_invite_binding"
down_revision = "0006_capability_review_note"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    tables = _tables()
    if "invite_binding_profiles" not in tables:
        op.create_table(
            "invite_binding_profiles",
            sa.Column("invite_id", sa.String(length=36), sa.ForeignKey("invite_tokens.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("company_name_snapshot", sa.String(length=128), nullable=False),
            sa.Column("owner_name_snapshot", sa.String(length=64), nullable=True),
            sa.Column("bound_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("bound_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("target_phone_hash", sa.String(length=64), nullable=True),
            sa.Column("match_source", sa.String(length=32), nullable=True),
            *_timestamps(),
        )
        op.create_index("ix_invite_binding_profiles_company_id", "invite_binding_profiles", ["company_id"])
        op.create_index("ix_invite_binding_profiles_bound_user_id", "invite_binding_profiles", ["bound_user_id"])
        op.create_index("ix_invite_binding_profiles_target_phone_hash", "invite_binding_profiles", ["target_phone_hash"])

    if "invite_confirmation_intents" not in tables:
        op.create_table(
            "invite_confirmation_intents",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("invite_id", sa.String(length=36), sa.ForeignKey("invite_tokens.id", ondelete="CASCADE"), nullable=False),
            sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("purpose", sa.String(length=64), nullable=False),
            sa.Column("nonce_hash", sa.String(length=64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            *_timestamps(),
        )
        op.create_index("ix_invite_confirmation_intents_invite_id", "invite_confirmation_intents", ["invite_id"])
        op.create_index("ix_invite_confirmation_intents_company_id", "invite_confirmation_intents", ["company_id"])
        op.create_index("ix_invite_confirmation_intents_expires_at", "invite_confirmation_intents", ["expires_at"])
        op.create_index("ix_invite_confirmation_intents_used_at", "invite_confirmation_intents", ["used_at"])
        op.create_index(
            "ix_invite_confirmation_active_lookup",
            "invite_confirmation_intents",
            ["invite_id", "purpose", "used_at", "expires_at"],
        )

    if "invite_delivery_attempts" not in tables:
        op.create_table(
            "invite_delivery_attempts",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("invite_id", sa.String(length=36), sa.ForeignKey("invite_tokens.id", ondelete="CASCADE"), nullable=False),
            sa.Column("channel", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("requested_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("provider_reference", sa.String(length=128), nullable=True),
            sa.Column("error_code", sa.String(length=64), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            *_timestamps(),
        )
        op.create_index("ix_invite_delivery_attempts_invite_id", "invite_delivery_attempts", ["invite_id"])
        op.create_index("ix_invite_delivery_attempts_channel", "invite_delivery_attempts", ["channel"])
        op.create_index("ix_invite_delivery_attempts_status", "invite_delivery_attempts", ["status"])
        op.create_index("ix_invite_delivery_attempts_requested_by", "invite_delivery_attempts", ["requested_by"])

    if "invite_match_attempts" not in tables:
        op.create_table(
            "invite_match_attempts",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("requested_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("phone_hash", sa.String(length=64), nullable=True),
            sa.Column("query_text", sa.Text(), nullable=True),
            sa.Column("region_code", sa.String(length=32), nullable=True),
            sa.Column("selected_company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
            sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("outcome", sa.String(length=64), nullable=False),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            *_timestamps(),
        )
        op.create_index("ix_invite_match_attempts_source", "invite_match_attempts", ["source"])
        op.create_index("ix_invite_match_attempts_requested_by", "invite_match_attempts", ["requested_by"])
        op.create_index("ix_invite_match_attempts_phone_hash", "invite_match_attempts", ["phone_hash"])
        op.create_index("ix_invite_match_attempts_region_code", "invite_match_attempts", ["region_code"])
        op.create_index("ix_invite_match_attempts_selected_company_id", "invite_match_attempts", ["selected_company_id"])
        op.create_index("ix_invite_match_attempts_outcome", "invite_match_attempts", ["outcome"])


def downgrade() -> None:
    tables = _tables()
    for table in [
        "invite_match_attempts",
        "invite_delivery_attempts",
        "invite_confirmation_intents",
        "invite_binding_profiles",
    ]:
        if table in tables:
            op.drop_table(table)

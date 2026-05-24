"""buyer onboarding

Revision ID: 002
Revises:
Create Date: 2026-05-21

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migration_utils import column_exists, table_exists

revision: str = "002"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

buyer_onboarding_status = postgresql.ENUM(
    "draft", "pending", "approved", "rejected", "suspended",
    name="buyer_onboarding_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE buyer_onboarding_status AS ENUM (
                'draft', 'pending', 'approved', 'rejected', 'suspended'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    org_columns: list[tuple[str, sa.Column]] = [
        ("city", sa.Column("city", sa.String(100), nullable=True)),
        ("industry", sa.Column("industry", sa.String(128), nullable=True)),
        ("website", sa.Column("website", sa.String(512), nullable=True)),
        ("procurement_contact", sa.Column("procurement_contact", sa.String(255), nullable=True)),
        ("job_title", sa.Column("job_title", sa.String(128), nullable=True)),
        (
            "onboarding_status",
            sa.Column(
                "onboarding_status",
                buyer_onboarding_status,
                nullable=False,
                server_default="draft",
            ),
        ),
        (
            "onboarding_submitted_at",
            sa.Column("onboarding_submitted_at", sa.DateTime(timezone=True), nullable=True),
        ),
    ]
    for name, col in org_columns:
        if not column_exists("buyer_organizations", name):
            op.add_column("buyer_organizations", col)

    if not table_exists("buyer_registration_drafts"):
        op.create_table(
            "buyer_registration_drafts",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("version", sa.Integer(), server_default="1", nullable=False),
            sa.Column("buyer_account_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
            sa.Column("step", sa.String(64), nullable=False),
            sa.Column("payload", postgresql.JSONB(), nullable=True),
        )
    elif column_exists("buyer_registration_drafts", "user_id") and not column_exists(
        "buyer_registration_drafts", "buyer_account_id"
    ):
        op.alter_column(
            "buyer_registration_drafts",
            "user_id",
            new_column_name="buyer_account_id",
        )



def downgrade() -> None:
    if table_exists("buyer_registration_drafts"):
        op.drop_table("buyer_registration_drafts")
    for col in (
        "onboarding_submitted_at",
        "onboarding_status",
        "job_title",
        "procurement_contact",
        "website",
        "industry",
        "city",
    ):
        if column_exists("buyer_organizations", col):
            op.drop_column("buyer_organizations", col)
    op.execute("DROP TYPE IF EXISTS buyer_onboarding_status")

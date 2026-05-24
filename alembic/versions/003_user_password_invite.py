"""account password invite columns

Revision ID: 003
Revises: 002
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migration_utils import column_exists, table_exists

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("buyer_accounts", "supplier_accounts", "admin_accounts"):
        if table_exists(table) and not column_exists(table, "must_change_password"):
            op.add_column(
                table,
                sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default="false"),
            )

    if table_exists("admin_accounts"):
        if not column_exists("admin_accounts", "invited_at"):
            op.add_column("admin_accounts", sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True))
        if not column_exists("admin_accounts", "invited_by"):
            op.add_column(
                "admin_accounts",
                sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=True),
            )

    # Legacy: older revisions targeted a `users` table
    if table_exists("users"):
        if not column_exists("users", "must_change_password"):
            op.add_column(
                "users",
                sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default="false"),
            )
        if not column_exists("users", "invited_at"):
            op.add_column("users", sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True))
        if not column_exists("users", "invited_by"):
            op.add_column("users", sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    for table in ("buyer_accounts", "supplier_accounts", "admin_accounts"):
        if table_exists(table) and column_exists(table, "must_change_password"):
            op.drop_column(table, "must_change_password")
    if table_exists("admin_accounts"):
        if column_exists("admin_accounts", "invited_by"):
            op.drop_column("admin_accounts", "invited_by")
        if column_exists("admin_accounts", "invited_at"):
            op.drop_column("admin_accounts", "invited_at")
    if table_exists("users"):
        for col in ("invited_by", "invited_at", "must_change_password"):
            if column_exists("users", col):
                op.drop_column("users", col)

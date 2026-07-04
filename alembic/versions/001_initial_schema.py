"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-27

Creates all application tables on fresh databases. Idempotent: skips when
tables already exist (legacy setups that used Base.metadata.create_all).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from migration_utils import table_exists

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if table_exists("buyer_organizations"):
        return

    import app.models  # noqa: F401 — register all models
    from app.core.shared.database import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    pass

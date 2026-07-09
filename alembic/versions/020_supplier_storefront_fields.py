"""Add supplier storefront profile fields and certification sort order."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020_supplier_storefront_fields"
down_revision: Union[str, None] = "019_browse_audit_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns(table)}
    if column.name not in cols:
        op.add_column(table, column)


def upgrade() -> None:
    _add_column_if_missing(
        "supplier_organizations",
        sa.Column("banner_url", sa.String(length=512), nullable=True),
    )
    _add_column_if_missing(
        "supplier_organizations",
        sa.Column("logo_url", sa.String(length=512), nullable=True),
    )
    _add_column_if_missing(
        "supplier_organizations",
        sa.Column("established_year", sa.SmallInteger(), nullable=True),
    )
    _add_column_if_missing(
        "supplier_organizations",
        sa.Column("team_size", sa.String(length=32), nullable=True),
    )
    _add_column_if_missing(
        "supplier_organizations",
        sa.Column("export_markets", sa.String(length=512), nullable=True),
    )
    _add_column_if_missing(
        "supplier_certifications",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    pass

"""Add missing AuditMixin columns to browse tables."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "019_browse_audit_columns"
down_revision: Union[str, None] = "018_buyer_browse_features"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_audit_columns(table: str) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns(table)}
    if "deleted_by" not in cols:
        op.add_column(table, sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True))
    if "version" not in cols:
        op.add_column(
            table,
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )


def upgrade() -> None:
    _add_audit_columns("export_hub_browse_settings")
    _add_audit_columns("export_hub_product_reviews")


def downgrade() -> None:
    pass

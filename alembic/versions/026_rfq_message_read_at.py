"""Add per-party message last-read timestamps on rfqs."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "026_rfq_message_read_at"
down_revision: Union[str, None] = "025_export_checklist_documents"
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
        "rfqs",
        sa.Column("supplier_messages_read_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        "rfqs",
        sa.Column("buyer_messages_read_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "rfqs" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("rfqs")}
    if "supplier_messages_read_at" in cols:
        op.drop_column("rfqs", "supplier_messages_read_at")
    if "buyer_messages_read_at" in cols:
        op.drop_column("rfqs", "buyer_messages_read_at")

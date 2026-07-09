"""Add admin-relay moderation fields to rfq_messages; drop the unused flat
conversation (buyer/supplier <-> MIU) tables now that all messaging is
scoped to an RFQ/Order thread and relayed through MIU Admin.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "022_rfq_message_moderation"
down_revision: Union[str, None] = "021_supplier_banner_style"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MESSAGE_REVIEW_STATUS = postgresql.ENUM(
    "pending", "routed", "reverted", name="message_review_status", create_type=False
)


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns(table)}
    if column.name not in cols:
        op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "rfq_messages" in insp.get_table_names():
        MESSAGE_REVIEW_STATUS.create(bind, checkfirst=True)
        _add_column_if_missing(
            "rfq_messages",
            sa.Column(
                "review_status",
                MESSAGE_REVIEW_STATUS,
                nullable=False,
                server_default="routed",
            ),
        )
        _add_column_if_missing("rfq_messages", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        _add_column_if_missing("rfq_messages", sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True))
        _add_column_if_missing("rfq_messages", sa.Column("admin_note", sa.Text(), nullable=True))
        _add_column_if_missing("rfq_messages", sa.Column("revert_note", sa.Text(), nullable=True))

    for table in ("conversation_messages", "conversation_threads"):
        if table in insp.get_table_names():
            op.drop_table(table)

    for enum_name in ("conversation_type", "message_sender_role"):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)


def downgrade() -> None:
    pass

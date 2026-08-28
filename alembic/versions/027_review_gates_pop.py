"""Admin review gates for product listings and supplier quotes, plus
multi-proof-of-payment capture on orders.

- product_status gains PENDING_REVIEW / REJECTED; products gain review columns.
- quote_status gains PENDING_REVIEW / RETURNED; rfq_quotes gain review columns.
- New order_payment_proofs table (many proofs per order).

Note the legacy ``product_status`` and ``quote_status`` Postgres enums store
member *names* (uppercase), not values, so new labels are added in that form.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "027_review_gates_pop"
down_revision: Union[str, None] = "026_rfq_message_read_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_ENUM_LABELS: dict[str, tuple[str, ...]] = {
    "product_status": ("PENDING_REVIEW", "REJECTED"),
    "quote_status": ("PENDING_REVIEW", "RETURNED"),
}


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return
    if column.name not in {c["name"] for c in insp.get_columns(table)}:
        op.add_column(table, column)


def _add_enum_labels(enum_name: str, labels: Sequence[str]) -> None:
    bind = op.get_bind()
    existing = {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = :name"
            ),
            {"name": enum_name},
        )
    }
    if not existing:
        return
    for label in labels:
        if label not in existing:
            op.execute(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{label}'")


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    for enum_name, labels in NEW_ENUM_LABELS.items():
        _add_enum_labels(enum_name, labels)

    _add_column_if_missing(
        "products", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True)
    )
    _add_column_if_missing(
        "products", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    _add_column_if_missing(
        "products", sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True)
    )
    _add_column_if_missing("products", sa.Column("review_note", sa.Text(), nullable=True))

    _add_column_if_missing(
        "rfq_quotes", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True)
    )
    _add_column_if_missing(
        "rfq_quotes", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    _add_column_if_missing(
        "rfq_quotes", sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True)
    )
    _add_column_if_missing("rfq_quotes", sa.Column("admin_remarks", sa.Text(), nullable=True))

    if "order_payment_proofs" not in insp.get_table_names():
        op.create_table(
            "order_payment_proofs",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("reference_no", sa.String(length=48), nullable=False),
            sa.Column("payment_type", sa.String(length=32), nullable=False),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.Column(
                "currency", sa.String(length=10), nullable=False, server_default="UGX"
            ),
            sa.Column("method", sa.String(length=64), nullable=True),
            sa.Column("payment_reference", sa.String(length=128), nullable=True),
            sa.Column("paid_at", sa.Date(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("file_name", sa.String(length=255), nullable=True),
            sa.Column(
                "send_attachment", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "notify_buyer", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "notify_supplier", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )
        op.create_index(
            "ix_order_payment_proofs_order_id", "order_payment_proofs", ["order_id"]
        )
        op.create_index(
            "ix_order_payment_proofs_reference_no",
            "order_payment_proofs",
            ["reference_no"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "order_payment_proofs" in insp.get_table_names():
        op.drop_table("order_payment_proofs")
    for table, columns in (
        ("products", ("submitted_at", "reviewed_at", "reviewed_by", "review_note")),
        ("rfq_quotes", ("submitted_at", "reviewed_at", "reviewed_by", "admin_remarks")),
    ):
        if table not in insp.get_table_names():
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        for column in columns:
            if column in existing:
                op.drop_column(table, column)
    # Postgres cannot drop enum labels; PENDING_REVIEW/RETURNED/REJECTED remain.

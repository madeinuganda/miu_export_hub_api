"""Idempotent migration helpers for databases seeded via Base.metadata.create_all."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


def column_exists(table: str, column: str, schema: str = "public") -> bool:
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table AND column_name = :column
            """
        ),
        {"schema": schema, "table": table, "column": column},
    ).first()
    return row is not None


def table_exists(table: str, schema: str = "public") -> bool:
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = :schema AND table_name = :table
            """
        ),
        {"schema": schema, "table": table},
    ).first()
    return row is not None


def index_exists(index_name: str, schema: str = "public") -> bool:
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname = :schema AND indexname = :index
            """
        ),
        {"schema": schema, "index": index_name},
    ).first()
    return row is not None

"""Add featured flag to export hub products."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016_product_featured"
down_revision: Union[str, None] = "015_category_images"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "products" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("products")}
    if "featured" not in cols:
        op.add_column(
            "products",
            sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    pass

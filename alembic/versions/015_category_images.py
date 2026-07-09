"""Add image_url and thumb_url to export hub categories."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_category_images"
down_revision: Union[str, None] = "014_ecommerce_extras"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "categories" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("categories")}
    if "image_url" not in cols:
        op.add_column("categories", sa.Column("image_url", sa.String(512), nullable=True))
    if "thumb_url" not in cols:
        op.add_column("categories", sa.Column("thumb_url", sa.String(512), nullable=True))


def downgrade() -> None:
    pass

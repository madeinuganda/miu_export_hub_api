"""Add testimonial CMS fields for export hub landing page."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017_testimonial_fields"
down_revision: Union[str, None] = "016_product_featured"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "cms_testimonials" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("cms_testimonials")}
    if "detail" not in cols:
        op.add_column("cms_testimonials", sa.Column("detail", sa.String(255), nullable=True))
    if "role_type" not in cols:
        op.add_column(
            "cms_testimonials",
            sa.Column("role_type", sa.String(16), nullable=False, server_default="supplier"),
        )
    if "metric" not in cols:
        op.add_column("cms_testimonials", sa.Column("metric", sa.String(128), nullable=True))
    if "rating" not in cols:
        op.add_column(
            "cms_testimonials",
            sa.Column("rating", sa.Integer(), nullable=False, server_default="5"),
        )


def downgrade() -> None:
    pass

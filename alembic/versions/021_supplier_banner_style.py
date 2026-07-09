"""Add banner_style preset key to supplier organizations."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021_supplier_banner_style"
down_revision: Union[str, None] = "020_supplier_storefront_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "supplier_organizations" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("supplier_organizations")}
    if "banner_style" not in cols:
        op.add_column(
            "supplier_organizations",
            sa.Column("banner_style", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    pass

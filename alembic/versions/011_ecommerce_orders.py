"""E-commerce orders, payment requests, and cart shipping."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "011_ecommerce_orders"
down_revision: Union[str, None] = "010_ecommerce_cart"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    import app.models  # noqa: F401
    import app.models.ecommerce.orders  # noqa: F401
    from app.core.shared.database import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    pass

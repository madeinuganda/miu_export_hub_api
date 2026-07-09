"""E-commerce reviews, per-shop shipping, and customer notifications."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "014_ecommerce_extras"
down_revision: Union[str, None] = "013_ecommerce_coupons_wallet"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    import app.models  # noqa: F401
    import app.models.ecommerce.notifications  # noqa: F401
    import app.models.ecommerce.reviews  # noqa: F401
    import app.models.ecommerce.shipping_config  # noqa: F401
    from app.core.shared.database import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    pass

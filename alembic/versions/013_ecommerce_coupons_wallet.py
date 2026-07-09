"""E-commerce coupons and wallet."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_ecommerce_coupons_wallet"
down_revision: Union[str, None] = "012_ecommerce_shipping_addresses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    import app.models  # noqa: F401
    import app.models.ecommerce.promotions  # noqa: F401
    import app.models.ecommerce.wallet  # noqa: F401
    from app.core.shared.database import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    insp = sa.inspect(bind)
    if "customer_accounts" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("customer_accounts")}
        if "wallet_balance" not in cols:
            op.add_column(
                "customer_accounts",
                sa.Column("wallet_balance", sa.Numeric(18, 2), server_default="0", nullable=False),
            )
    if "ecommerce_orders" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("ecommerce_orders")}
        if "coupon_code" not in cols:
            op.add_column("ecommerce_orders", sa.Column("coupon_code", sa.String(32), nullable=True))
        if "coupon_discount" not in cols:
            op.add_column(
                "ecommerce_orders",
                sa.Column("coupon_discount", sa.Numeric(18, 2), server_default="0", nullable=False),
            )
    if "ecommerce_payment_requests" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("ecommerce_payment_requests")}
        if "purpose" not in cols:
            op.add_column(
                "ecommerce_payment_requests",
                sa.Column("purpose", sa.String(32), server_default="order_checkout", nullable=False),
            )


def downgrade() -> None:
    pass

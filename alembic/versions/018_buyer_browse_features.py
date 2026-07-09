"""Buyer browse features: featured flags, deals, reviews, browse settings."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018_buyer_browse_features"
down_revision: Union[str, None] = "017_testimonial_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "categories" in tables:
        cols = {c["name"] for c in insp.get_columns("categories")}
        if "featured" not in cols:
            op.add_column(
                "categories",
                sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()),
            )

    if "supplier_organizations" in tables:
        cols = {c["name"] for c in insp.get_columns("supplier_organizations")}
        if "featured" not in cols:
            op.add_column(
                "supplier_organizations",
                sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()),
            )

    if "products" in tables:
        cols = {c["name"] for c in insp.get_columns("products")}
        if "is_top_deal" not in cols:
            op.add_column(
                "products",
                sa.Column("is_top_deal", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
        if "deal_price" not in cols:
            op.add_column("products", sa.Column("deal_price", sa.Numeric(18, 2), nullable=True))

    if "export_hub_product_reviews" not in tables:
        op.create_table(
            "export_hub_product_reviews",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("product_id", sa.UUID(), nullable=False),
            sa.Column("buyer_org_id", sa.UUID(), nullable=False),
            sa.Column("buyer_account_id", sa.UUID(), nullable=False),
            sa.Column("order_id", sa.UUID(), nullable=True),
            sa.Column("rating", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(128), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("reviewer_name", sa.String(128), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.UUID(), nullable=True),
            sa.Column("updated_by", sa.UUID(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", sa.UUID(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("product_id", "buyer_org_id", name="uq_export_hub_product_review"),
        )
        op.create_index("ix_export_hub_product_reviews_product_id", "export_hub_product_reviews", ["product_id"])
        op.create_index("ix_export_hub_product_reviews_buyer_org_id", "export_hub_product_reviews", ["buyer_org_id"])

    if "export_hub_browse_settings" not in tables:
        op.create_table(
            "export_hub_browse_settings",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("ranking_rating_weight", sa.Numeric(5, 2), nullable=False, server_default="0.70"),
            sa.Column("ranking_review_weight", sa.Numeric(5, 2), nullable=False, server_default="0.30"),
            sa.Column("top_deals_limit", sa.Integer(), nullable=False, server_default="4"),
            sa.Column("top_ranking_limit", sa.Integer(), nullable=False, server_default="4"),
            sa.Column("featured_suppliers_limit", sa.Integer(), nullable=False, server_default="4"),
            sa.Column("featured_categories_limit", sa.Integer(), nullable=False, server_default="8"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.UUID(), nullable=True),
            sa.Column("updated_by", sa.UUID(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", sa.UUID(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    pass

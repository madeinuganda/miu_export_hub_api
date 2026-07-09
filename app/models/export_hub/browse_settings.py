from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.shared.database import Base
from app.models.shared.base import AuditMixin


class ExportHubBrowseSettings(AuditMixin, Base):
    """Singleton-style config for buyer dashboard curated sections."""

    __tablename__ = "export_hub_browse_settings"

    ranking_rating_weight: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.70"), nullable=False)
    ranking_review_weight: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.30"), nullable=False)
    top_deals_limit: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    top_ranking_limit: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    featured_suppliers_limit: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    featured_categories_limit: Mapped[int] = mapped_column(Integer, default=8, nullable=False)

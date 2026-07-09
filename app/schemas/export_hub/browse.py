from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class BrowseSettingsUpdate(BaseModel):
    ranking_rating_weight: Decimal | None = Field(default=None, ge=0, le=1)
    ranking_review_weight: Decimal | None = Field(default=None, ge=0, le=1)
    top_deals_limit: int | None = Field(default=None, ge=1, le=24)
    top_ranking_limit: int | None = Field(default=None, ge=1, le=24)
    featured_suppliers_limit: int | None = Field(default=None, ge=1, le=24)
    featured_categories_limit: int | None = Field(default=None, ge=1, le=48)


class BrowseSettingsItem(BaseModel):
    ranking_rating_weight: Decimal
    ranking_review_weight: Decimal
    top_deals_limit: int
    top_ranking_limit: int
    featured_suppliers_limit: int
    featured_categories_limit: int


class FeaturedFlagUpdate(BaseModel):
    featured: bool


class TopDealUpdate(BaseModel):
    is_top_deal: bool
    deal_price: Decimal | None = None

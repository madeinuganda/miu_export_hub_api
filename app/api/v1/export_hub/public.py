from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.database import get_db
from app.services.export_hub.catalog_service import CatalogService
from app.services.export_hub.marketplace_service import MarketplaceService
from app.services.export_hub.testimonial_service import TestimonialService
from app.schemas.export_hub.testimonial import PublicTestimonialListResponse

router = APIRouter(prefix="/public")


@router.get("/home")
async def public_home(db: AsyncSession = Depends(get_db)):
    return await MarketplaceService.get_public_home(db)


@router.get("/categories")
async def public_categories(db: AsyncSession = Depends(get_db)):
    home = await MarketplaceService.get_public_home(db)
    return {"categories": home["categories"]}


@router.get("/products/featured")
async def featured_products(
    limit: int = Query(12, ge=1, le=48),
    db: AsyncSession = Depends(get_db),
):
    return {"items": await MarketplaceService.get_featured_products(db, limit=limit)}


@router.get("/testimonials", response_model=PublicTestimonialListResponse)
async def public_testimonials(db: AsyncSession = Depends(get_db)):
    return await TestimonialService.list_public_testimonials(db)


@router.get("/products/{product_id}")
async def public_product(product_id: UUID, db: AsyncSession = Depends(get_db)):
    return await CatalogService.buyer_product_detail(db, product_id, reveal_supplier=False)


@router.get("/site-settings")
async def site_settings(db: AsyncSession = Depends(get_db)):
    home = await MarketplaceService.get_public_home(db)
    return home.get("siteSettings", {})

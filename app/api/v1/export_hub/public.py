from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.database import get_db
from app.services.export_hub.catalog_service import CatalogService
from app.services.export_hub.marketplace_service import MarketplaceService

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/home")
async def public_home(db: AsyncSession = Depends(get_db)):
    return await MarketplaceService.get_public_home(db)


@router.get("/categories")
async def public_categories(db: AsyncSession = Depends(get_db)):
    home = await MarketplaceService.get_public_home(db)
    return {"categories": home["categories"]}


@router.get("/products/featured")
async def featured_products(db: AsyncSession = Depends(get_db)):
    return {"items": await MarketplaceService.get_featured_products(db)}


@router.get("/products/{product_id}")
async def public_product(product_id: UUID, db: AsyncSession = Depends(get_db)):
    return await CatalogService.buyer_product_detail(db, product_id, reveal_supplier=False)


@router.get("/site-settings")
async def site_settings(db: AsyncSession = Depends(get_db)):
    home = await MarketplaceService.get_public_home(db)
    return home.get("siteSettings", {})

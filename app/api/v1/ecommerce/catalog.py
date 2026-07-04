from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.database import get_db
from app.schemas.ecommerce.catalog import GuestIdResponse, ProductFilterQuery, ProductSearchQuery
from app.services.ecommerce.catalog_service import EcommerceCatalogService

router = APIRouter(tags=["E-Commerce · Catalog"])


@router.get("/get-guest-id", response_model=GuestIdResponse)
async def get_guest_id(db: AsyncSession = Depends(get_db)):
    guest_id = await EcommerceCatalogService.create_guest_id(db)
    await db.commit()
    return GuestIdResponse(guest_id=guest_id)


@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    return await EcommerceCatalogService.list_categories(db)


@router.get("/categories/products/{category_id}")
async def category_products(
    category_id: UUID,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(1, ge=1),
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceCatalogService.list_category_products(
        db, category_id, limit=limit, offset=offset, search=search
    )


@router.get("/products/latest")
async def products_latest(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceCatalogService.list_latest(db, limit=limit, offset=offset)


@router.get("/products/featured")
async def products_featured(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceCatalogService.list_featured(db, limit=limit, offset=offset)


@router.get("/products/search")
async def products_search(
    name: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceCatalogService.search_products(db, name=name, limit=limit, offset=offset)


@router.post("/products/search")
async def products_search_post(body: ProductSearchQuery, db: AsyncSession = Depends(get_db)):
    return await EcommerceCatalogService.search_products(
        db, name=body.name, limit=body.limit, offset=body.offset
    )


@router.get("/products/filter")
async def products_filter_get(
    search: str | None = None,
    category: list[UUID] | None = Query(None),
    brand: list[UUID] | None = Query(None),
    sort_by: str | None = Query(None, pattern="^(low-high|high-low|a-z|z-a|latest)$"),
    price_min: Decimal | None = None,
    price_max: Decimal | None = None,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceCatalogService.filter_products(
        db,
        search=search,
        category_ids=category,
        brand_ids=brand,
        sort_by=sort_by,
        price_min=price_min,
        price_max=price_max,
        limit=limit,
        offset=offset,
    )


@router.post("/products/filter")
async def products_filter_post(body: ProductFilterQuery, db: AsyncSession = Depends(get_db)):
    return await EcommerceCatalogService.filter_products(
        db,
        search=body.search,
        category_ids=body.category,
        brand_ids=body.brand,
        sort_by=body.sort_by,
        price_min=body.price_min,
        price_max=body.price_max,
        limit=body.limit,
        offset=body.offset,
    )


@router.get("/products/details/{slug}")
async def product_details(slug: str, db: AsyncSession = Depends(get_db)):
    return await EcommerceCatalogService.product_detail(db, slug)


@router.get("/brands")
async def list_brands(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceCatalogService.list_brands(db, limit=limit, offset=offset)


@router.get("/brands/products/{brand_id}")
async def brand_products(
    brand_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceCatalogService.list_brand_products(db, brand_id, limit=limit, offset=offset)


@router.get("/banners")
async def list_banners(db: AsyncSession = Depends(get_db)):
    return await EcommerceCatalogService.list_banners(db)

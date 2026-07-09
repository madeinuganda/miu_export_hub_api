from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.models.ecommerce.accounts import EcommerceShop
from app.models.ecommerce.catalog import EcommerceProduct
from app.models.shared.enums import EcommerceProductStatus
from app.services.ecommerce.catalog_service import EcommerceCatalogService


class EcommerceShopService:
  @staticmethod
  async def get_shop_by_slug(db: AsyncSession, slug: str) -> dict:
    shop = (
      await db.execute(
        select(EcommerceShop).where(
          EcommerceShop.slug == slug,
          EcommerceShop.deleted_at.is_(None),
          EcommerceShop.is_published.is_(True),
        )
      )
    ).scalar_one_or_none()
    if not shop:
      raise AppError(404, "Shop not found", "not_found")
    return {
      "id": str(shop.id),
      "name": shop.name,
      "slug": shop.slug,
      "tagline": shop.tagline,
      "is_published": shop.is_published,
    }

  @staticmethod
  async def list_shop_products(
    db: AsyncSession, slug: str, *, limit: int = 20, offset: int = 1, search: str | None = None
  ) -> dict:
    shop = (
      await db.execute(
        select(EcommerceShop).where(
          EcommerceShop.slug == slug,
          EcommerceShop.deleted_at.is_(None),
          EcommerceShop.is_published.is_(True),
        )
      )
    ).scalar_one_or_none()
    if not shop:
      raise AppError(404, "Shop not found", "not_found")

    filters = [
      EcommerceProduct.shop_id == shop.id,
      EcommerceProduct.deleted_at.is_(None),
      EcommerceProduct.status == EcommerceProductStatus.PUBLISHED,
    ]
    if search:
      filters.append(EcommerceProduct.name.ilike(f"%{search}%"))
    base = select(EcommerceProduct).where(*filters)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
      await db.execute(
        base.order_by(EcommerceProduct.created_at.desc()).offset((offset - 1) * limit).limit(limit)
      )
    ).scalars().all()
    products = [await EcommerceCatalogService._product_card(db, p) for p in rows]
    return {
      "shop": {
        "id": str(shop.id),
        "name": shop.name,
        "slug": shop.slug,
        "tagline": shop.tagline,
      },
      "total_size": total,
      "limit": limit,
      "offset": offset,
      "products": products,
    }

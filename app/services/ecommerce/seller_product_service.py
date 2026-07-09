from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.models.ecommerce.accounts import EcommerceShop, SellerAccount
from app.models.ecommerce.catalog import EcommerceProduct
from app.schemas.ecommerce.admin import slugify
from app.schemas.ecommerce.seller_product import (
    SellerProductCreateRequest,
    SellerProductUpdateRequest,
    SellerStockUpdateRequest,
)
from app.utils.audit import apply_create_audit, apply_update_audit


class EcommerceSellerProductService:
  @staticmethod
  async def _shop_for_seller(db: AsyncSession, seller: SellerAccount) -> EcommerceShop:
    shop = (
      await db.execute(
        select(EcommerceShop).where(
          EcommerceShop.seller_account_id == seller.id,
          EcommerceShop.deleted_at.is_(None),
        )
      )
    ).scalar_one_or_none()
    if not shop:
      raise AppError(404, "Shop not found for seller", "shop_not_found")
    return shop

  @staticmethod
  async def list_products(
    db: AsyncSession, seller: SellerAccount, *, limit: int = 20, offset: int = 1
  ) -> dict:
    shop = await EcommerceSellerProductService._shop_for_seller(db, seller)
    base = select(EcommerceProduct).where(
      EcommerceProduct.shop_id == shop.id,
      EcommerceProduct.deleted_at.is_(None),
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
      await db.execute(
        base.order_by(EcommerceProduct.created_at.desc()).offset((offset - 1) * limit).limit(limit)
      )
    ).scalars().all()
    return {
      "shop_id": str(shop.id),
      "total_size": total,
      "products": [
        {
          "id": str(p.id),
          "name": p.name,
          "slug": p.slug,
          "status": p.status.value,
          "unit_price": float(p.unit_price),
          "current_stock": p.current_stock,
          "stock_status": p.stock_status.value,
        }
        for p in rows
      ],
    }

  @staticmethod
  async def create_product(
    db: AsyncSession, seller: SellerAccount, data: SellerProductCreateRequest
  ) -> dict:
    shop = await EcommerceSellerProductService._shop_for_seller(db, seller)
    slug = data.slug or slugify(data.name)
    row = EcommerceProduct(
      shop_id=shop.id,
      name=data.name,
      code=data.code,
      slug=slug,
      category_id=data.category_id,
      sub_category_id=data.sub_category_id,
      sub_sub_category_id=data.sub_sub_category_id,
      brand_id=data.brand_id,
      unit_price=data.unit_price,
      discount=data.discount,
      discount_type=data.discount_type,
      thumbnail_url=data.thumbnail_url,
      details=data.details,
      status=data.status,
      featured=data.featured,
      current_stock=data.current_stock,
      minimum_order_qty=data.minimum_order_qty,
      stock_status=data.stock_status,
    )
    apply_create_audit(row, seller.id)
    db.add(row)
    await db.flush()
    return {"id": str(row.id), "slug": row.slug}

  @staticmethod
  async def update_product(
    db: AsyncSession,
    seller: SellerAccount,
    product_id: UUID,
    data: SellerProductUpdateRequest,
  ) -> dict:
    shop = await EcommerceSellerProductService._shop_for_seller(db, seller)
    row = (
      await db.execute(
        select(EcommerceProduct).where(
          EcommerceProduct.id == product_id,
          EcommerceProduct.shop_id == shop.id,
          EcommerceProduct.deleted_at.is_(None),
        )
      )
    ).scalar_one_or_none()
    if not row:
      raise AppError(404, "Product not found", "not_found")
    for field in (
      "name", "code", "slug", "category_id", "sub_category_id", "sub_sub_category_id",
      "brand_id", "unit_price", "discount", "discount_type", "thumbnail_url", "details",
      "status", "featured", "current_stock", "minimum_order_qty", "stock_status",
    ):
      value = getattr(data, field)
      if value is not None:
        setattr(row, field, value)
    apply_update_audit(row, seller.id)
    await db.flush()
    return {"id": str(row.id), "message": "updated"}

  @staticmethod
  async def update_stock(
    db: AsyncSession,
    seller: SellerAccount,
    product_id: UUID,
    data: SellerStockUpdateRequest,
  ) -> dict:
    shop = await EcommerceSellerProductService._shop_for_seller(db, seller)
    row = (
      await db.execute(
        select(EcommerceProduct).where(
          EcommerceProduct.id == product_id,
          EcommerceProduct.shop_id == shop.id,
          EcommerceProduct.deleted_at.is_(None),
        )
      )
    ).scalar_one_or_none()
    if not row:
      raise AppError(404, "Product not found", "not_found")
    row.current_stock = data.current_stock
    if data.stock_status is not None:
      row.stock_status = data.stock_status
    apply_update_audit(row, seller.id)
    await db.flush()
    return {"id": str(row.id), "current_stock": row.current_stock}

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.core.shared.security import hash_password
from app.models.ecommerce.accounts import EcommerceShop, SellerAccount
from app.models.ecommerce.shipping_config import EcommerceShopShippingMethod
from app.schemas.ecommerce.admin import ShopShippingMethodRequest, VendorCreateRequest, VendorUpdateRequest, slugify
from app.utils.audit import apply_create_audit, apply_update_audit


class EcommerceAdminVendorService:
  @staticmethod
  async def list_vendors(db: AsyncSession, *, limit: int = 20, offset: int = 1) -> dict:
    base = (
      select(SellerAccount, EcommerceShop)
      .outerjoin(
        EcommerceShop,
        (EcommerceShop.seller_account_id == SellerAccount.id)
        & (EcommerceShop.deleted_at.is_(None)),
      )
      .where(SellerAccount.deleted_at.is_(None))
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
      await db.execute(
        base.order_by(SellerAccount.created_at.desc()).offset((offset - 1) * limit).limit(limit)
      )
    ).all()
    vendors = []
    for seller, shop in rows:
      vendors.append(
        {
          "seller_id": str(seller.id),
          "email": seller.email,
          "first_name": seller.first_name,
          "last_name": seller.last_name,
          "is_active": seller.is_active,
          "shop": (
            {
              "id": str(shop.id),
              "name": shop.name,
              "slug": shop.slug,
              "is_published": shop.is_published,
            }
            if shop
            else None
          ),
        }
      )
    return {"total_size": total, "vendors": vendors}

  @staticmethod
  async def create_vendor(db: AsyncSession, data: VendorCreateRequest, actor_id: UUID) -> dict:
    existing = (
      await db.execute(
        select(SellerAccount).where(
          SellerAccount.email == data.email,
          SellerAccount.deleted_at.is_(None),
        )
      )
    ).scalar_one_or_none()
    if existing:
      raise AppError(409, "Seller email already exists", "email_taken")

    seller = SellerAccount(
      id=uuid4(),
      email=data.email,
      password_hash=hash_password(data.password),
      first_name=data.first_name,
      last_name=data.last_name,
      phone=data.phone,
      is_active=True,
    )
    apply_create_audit(seller, actor_id)
    db.add(seller)
    await db.flush()

    shop_slug = data.shop_slug or slugify(data.shop_name)
    shop = EcommerceShop(
      seller_account_id=seller.id,
      name=data.shop_name,
      slug=shop_slug,
      tagline=data.shop_tagline,
      is_published=data.is_published,
    )
    apply_create_audit(shop, actor_id)
    db.add(shop)
    await db.flush()
    return {"seller_id": str(seller.id), "shop_id": str(shop.id), "shop_slug": shop.slug}

  @staticmethod
  async def update_vendor(
    db: AsyncSession, seller_id: UUID, data: VendorUpdateRequest, actor_id: UUID
  ) -> dict:
    seller = await db.get(SellerAccount, seller_id)
    if not seller or seller.deleted_at:
      raise AppError(404, "Seller not found", "not_found")
    if data.first_name is not None:
      seller.first_name = data.first_name
    if data.last_name is not None:
      seller.last_name = data.last_name
    if data.phone is not None:
      seller.phone = data.phone
    if data.is_active is not None:
      seller.is_active = data.is_active
    apply_update_audit(seller, actor_id)

    shop = (
      await db.execute(
        select(EcommerceShop).where(
          EcommerceShop.seller_account_id == seller_id,
          EcommerceShop.deleted_at.is_(None),
        )
      )
    ).scalar_one_or_none()
    if shop:
      if data.shop_name is not None:
        shop.name = data.shop_name
      if data.shop_tagline is not None:
        shop.tagline = data.shop_tagline
      if data.is_published is not None:
        shop.is_published = data.is_published
      apply_update_audit(shop, actor_id)
    await db.flush()
    return {"seller_id": str(seller.id), "message": "updated"}

  @staticmethod
  async def list_shop_shipping(db: AsyncSession, shop_id: UUID) -> list[dict]:
    rows = (
      await db.execute(
        select(EcommerceShopShippingMethod)
        .where(
          EcommerceShopShippingMethod.shop_id == shop_id,
          EcommerceShopShippingMethod.deleted_at.is_(None),
        )
        .order_by(EcommerceShopShippingMethod.sort_order)
      )
    ).scalars().all()
    return [
      {
        "id": str(r.id),
        "code": r.code,
        "title": r.title,
        "duration": r.duration,
        "cost": float(r.cost),
        "currency": r.currency,
        "is_active": r.is_active,
      }
      for r in rows
    ]

  @staticmethod
  async def upsert_shop_shipping(
    db: AsyncSession, shop_id: UUID, data: ShopShippingMethodRequest, actor_id: UUID
  ) -> dict:
    shop = await db.get(EcommerceShop, shop_id)
    if not shop or shop.deleted_at:
      raise AppError(404, "Shop not found", "shop_not_found")
    existing = (
      await db.execute(
        select(EcommerceShopShippingMethod).where(
          EcommerceShopShippingMethod.shop_id == shop_id,
          EcommerceShopShippingMethod.code == data.code,
          EcommerceShopShippingMethod.deleted_at.is_(None),
        )
      )
    ).scalar_one_or_none()
    if existing:
      existing.title = data.title
      existing.duration = data.duration
      existing.cost = data.cost
      existing.currency = data.currency
      existing.is_active = data.is_active
      existing.sort_order = data.sort_order
      apply_update_audit(existing, actor_id)
      await db.flush()
      return {"id": str(existing.id), "message": "updated"}
    row = EcommerceShopShippingMethod(shop_id=shop_id, **data.model_dump())
    apply_create_audit(row, actor_id)
    db.add(row)
    await db.flush()
    return {"id": str(row.id), "message": "created"}

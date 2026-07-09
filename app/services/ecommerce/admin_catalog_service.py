from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.models.ecommerce.accounts import EcommerceShop
from app.models.ecommerce.catalog import (
    EcommerceBanner,
    EcommerceBrand,
    EcommerceCategory,
    EcommerceProduct,
)
from app.models.ecommerce.promotions import EcommerceCoupon
from app.schemas.ecommerce.admin import (
    AdminProductCreateRequest,
    AdminProductUpdateRequest,
    BannerCreateRequest,
    BannerUpdateRequest,
    BrandCreateRequest,
    BrandUpdateRequest,
    CategoryCreateRequest,
    CategoryUpdateRequest,
    CouponCreateRequest,
    CouponUpdateRequest,
    slugify,
)
from app.utils.audit import apply_create_audit, apply_update_audit


class EcommerceAdminCatalogService:
  @staticmethod
  async def list_categories(db: AsyncSession) -> list[dict]:
    rows = (
      await db.execute(
        select(EcommerceCategory)
        .where(EcommerceCategory.deleted_at.is_(None))
        .order_by(EcommerceCategory.priority.desc(), EcommerceCategory.name)
      )
    ).scalars().all()
    return [
      {
        "id": str(row.id),
        "name": row.name,
        "slug": row.slug,
        "parent_id": str(row.parent_id) if row.parent_id else None,
        "position": row.position.value,
        "is_active": row.is_active,
      }
      for row in rows
    ]

  @staticmethod
  async def create_category(db: AsyncSession, data: CategoryCreateRequest, actor_id: UUID) -> dict:
    slug = data.slug or slugify(data.name)
    existing = (
      await db.execute(
        select(EcommerceCategory).where(
          EcommerceCategory.slug == slug,
          EcommerceCategory.deleted_at.is_(None),
        )
      )
    ).scalar_one_or_none()
    if existing:
      raise AppError(409, "Category slug already exists", "slug_taken")
    row = EcommerceCategory(
      name=data.name,
      slug=slug,
      icon_url=data.icon_url,
      parent_id=data.parent_id,
      position=data.position,
      home_status=data.home_status,
      priority=data.priority,
      is_active=data.is_active,
    )
    apply_create_audit(row, actor_id)
    db.add(row)
    await db.flush()
    return {"id": str(row.id), "slug": row.slug}

  @staticmethod
  async def update_category(
    db: AsyncSession, category_id: UUID, data: CategoryUpdateRequest, actor_id: UUID
  ) -> dict:
    row = await db.get(EcommerceCategory, category_id)
    if not row or row.deleted_at:
      raise AppError(404, "Category not found", "not_found")
    if data.name is not None:
      row.name = data.name
    if data.slug is not None:
      row.slug = data.slug
    if data.icon_url is not None:
      row.icon_url = data.icon_url
    if data.parent_id is not None:
      row.parent_id = data.parent_id
    if data.home_status is not None:
      row.home_status = data.home_status
    if data.priority is not None:
      row.priority = data.priority
    if data.is_active is not None:
      row.is_active = data.is_active
    apply_update_audit(row, actor_id)
    await db.flush()
    return {"id": str(row.id), "message": "updated"}

  @staticmethod
  async def list_brands(db: AsyncSession, *, limit: int = 50, offset: int = 1) -> dict:
    base = select(EcommerceBrand).where(EcommerceBrand.deleted_at.is_(None))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
      await db.execute(base.order_by(EcommerceBrand.name).offset((offset - 1) * limit).limit(limit))
    ).scalars().all()
    return {
      "total_size": total,
      "brands": [{"id": str(r.id), "name": r.name, "slug": r.slug, "is_active": r.is_active} for r in rows],
    }

  @staticmethod
  async def create_brand(db: AsyncSession, data: BrandCreateRequest, actor_id: UUID) -> dict:
    slug = data.slug or slugify(data.name)
    row = EcommerceBrand(name=data.name, slug=slug, image_url=data.image_url, is_active=data.is_active)
    apply_create_audit(row, actor_id)
    db.add(row)
    await db.flush()
    return {"id": str(row.id), "slug": row.slug}

  @staticmethod
  async def update_brand(
    db: AsyncSession, brand_id: UUID, data: BrandUpdateRequest, actor_id: UUID
  ) -> dict:
    row = await db.get(EcommerceBrand, brand_id)
    if not row or row.deleted_at:
      raise AppError(404, "Brand not found", "not_found")
    if data.name is not None:
      row.name = data.name
    if data.slug is not None:
      row.slug = data.slug
    if data.image_url is not None:
      row.image_url = data.image_url
    if data.is_active is not None:
      row.is_active = data.is_active
    apply_update_audit(row, actor_id)
    await db.flush()
    return {"id": str(row.id), "message": "updated"}

  @staticmethod
  async def list_products(
    db: AsyncSession, *, shop_id: UUID | None = None, limit: int = 20, offset: int = 1
  ) -> dict:
    filters = [EcommerceProduct.deleted_at.is_(None)]
    if shop_id:
      filters.append(EcommerceProduct.shop_id == shop_id)
    base = select(EcommerceProduct).where(*filters)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
      await db.execute(
        base.order_by(EcommerceProduct.created_at.desc()).offset((offset - 1) * limit).limit(limit)
      )
    ).scalars().all()
    return {
      "total_size": total,
      "products": [
        {
          "id": str(p.id),
          "name": p.name,
          "slug": p.slug,
          "shop_id": str(p.shop_id),
          "status": p.status.value,
          "unit_price": float(p.unit_price),
          "current_stock": p.current_stock,
        }
        for p in rows
      ],
    }

  @staticmethod
  async def create_product(db: AsyncSession, data: AdminProductCreateRequest, actor_id: UUID) -> dict:
    shop = await db.get(EcommerceShop, data.shop_id)
    if not shop or shop.deleted_at:
      raise AppError(404, "Shop not found", "shop_not_found")
    slug = data.slug or slugify(data.name)
    row = EcommerceProduct(
      shop_id=data.shop_id,
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
    apply_create_audit(row, actor_id)
    db.add(row)
    await db.flush()
    return {"id": str(row.id), "slug": row.slug}

  @staticmethod
  async def update_product(
    db: AsyncSession, product_id: UUID, data: AdminProductUpdateRequest, actor_id: UUID
  ) -> dict:
    row = await db.get(EcommerceProduct, product_id)
    if not row or row.deleted_at:
      raise AppError(404, "Product not found", "not_found")
    for field in (
      "name", "code", "slug", "category_id", "sub_category_id", "sub_sub_category_id",
      "brand_id", "unit_price", "discount", "discount_type", "thumbnail_url", "details",
      "status", "featured", "current_stock", "minimum_order_qty", "stock_status",
    ):
      value = getattr(data, field)
      if value is not None:
        setattr(row, field, value)
    apply_update_audit(row, actor_id)
    await db.flush()
    return {"id": str(row.id), "message": "updated"}

  @staticmethod
  async def list_banners(db: AsyncSession) -> list[dict]:
    rows = (
      await db.execute(
        select(EcommerceBanner)
        .where(EcommerceBanner.deleted_at.is_(None))
        .order_by(EcommerceBanner.sort_order)
      )
    ).scalars().all()
    return [
      {
        "id": str(r.id),
        "title": r.title,
        "photo_url": r.photo_url,
        "is_published": r.is_published,
        "sort_order": r.sort_order,
      }
      for r in rows
    ]

  @staticmethod
  async def create_banner(db: AsyncSession, data: BannerCreateRequest, actor_id: UUID) -> dict:
    row = EcommerceBanner(**data.model_dump())
    apply_create_audit(row, actor_id)
    db.add(row)
    await db.flush()
    return {"id": str(row.id)}

  @staticmethod
  async def update_banner(
    db: AsyncSession, banner_id: UUID, data: BannerUpdateRequest, actor_id: UUID
  ) -> dict:
    row = await db.get(EcommerceBanner, banner_id)
    if not row or row.deleted_at:
      raise AppError(404, "Banner not found", "not_found")
    for field, value in data.model_dump(exclude_unset=True).items():
      setattr(row, field, value)
    apply_update_audit(row, actor_id)
    await db.flush()
    return {"id": str(row.id), "message": "updated"}

  @staticmethod
  async def list_coupons(db: AsyncSession, *, limit: int = 20, offset: int = 1) -> dict:
    base = select(EcommerceCoupon).where(EcommerceCoupon.deleted_at.is_(None))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
      await db.execute(
        base.order_by(EcommerceCoupon.created_at.desc()).offset((offset - 1) * limit).limit(limit)
      )
    ).scalars().all()
    return {
      "total_size": total,
      "coupons": [
        {
          "id": str(c.id),
          "title": c.title,
          "code": c.code,
          "coupon_type": c.coupon_type.value,
          "discount": float(c.discount),
          "is_active": c.is_active,
          "shop_id": str(c.shop_id) if c.shop_id else None,
        }
        for c in rows
      ],
    }

  @staticmethod
  async def create_coupon(db: AsyncSession, data: CouponCreateRequest, actor_id: UUID) -> dict:
    existing = (
      await db.execute(
        select(EcommerceCoupon).where(
          EcommerceCoupon.code == data.code.upper(),
          EcommerceCoupon.deleted_at.is_(None),
        )
      )
    ).scalar_one_or_none()
    if existing:
      raise AppError(409, "Coupon code already exists", "code_taken")
    row = EcommerceCoupon(
      title=data.title,
      code=data.code.upper(),
      coupon_type=data.coupon_type,
      discount_type=data.discount_type,
      discount=data.discount,
      max_discount=data.max_discount,
      min_purchase=data.min_purchase,
      shop_id=data.shop_id,
      customer_id=data.customer_id,
      start_date=date.fromisoformat(data.start_date),
      expire_date=date.fromisoformat(data.expire_date),
      usage_limit=data.usage_limit,
      total_limit=data.total_limit,
      is_active=data.is_active,
    )
    apply_create_audit(row, actor_id)
    db.add(row)
    await db.flush()
    return {"id": str(row.id), "code": row.code}

  @staticmethod
  async def update_coupon(
    db: AsyncSession, coupon_id: UUID, data: CouponUpdateRequest, actor_id: UUID
  ) -> dict:
    row = await db.get(EcommerceCoupon, coupon_id)
    if not row or row.deleted_at:
      raise AppError(404, "Coupon not found", "not_found")
    payload = data.model_dump(exclude_unset=True)
    if "start_date" in payload:
      row.start_date = date.fromisoformat(payload.pop("start_date"))
    if "expire_date" in payload:
      row.expire_date = date.fromisoformat(payload.pop("expire_date"))
    for field, value in payload.items():
      setattr(row, field, value)
    apply_update_audit(row, actor_id)
    await db.flush()
    return {"id": str(row.id), "message": "updated"}

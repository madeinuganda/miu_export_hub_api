from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.models.ecommerce.accounts import EcommerceShop
from app.models.ecommerce.catalog import (
    EcommerceBanner,
    EcommerceBrand,
    EcommerceCategory,
    EcommerceGuest,
    EcommerceProduct,
    EcommerceProductImage,
)
from app.models.shared.enums import EcommerceCategoryPosition, EcommerceProductStatus


class EcommerceCatalogService:
    @staticmethod
    def _sale_price(product: EcommerceProduct) -> Decimal:
        if product.discount <= 0:
            return product.unit_price
        if product.discount_type.value == "flat":
            return max(product.unit_price - product.discount, Decimal("0"))
        return max(product.unit_price * (Decimal("1") - product.discount / Decimal("100")), Decimal("0"))

    @staticmethod
    async def create_guest_id(db: AsyncSession) -> UUID:
        guest = EcommerceGuest(id=uuid4())
        db.add(guest)
        await db.flush()
        return guest.id

    @staticmethod
    def _active_filters():
        return (
            EcommerceProduct.deleted_at.is_(None),
            EcommerceProduct.status == EcommerceProductStatus.PUBLISHED,
        )

    @staticmethod
    async def _product_card(db: AsyncSession, product: EcommerceProduct) -> dict:
        img = (
            await db.execute(
                select(EcommerceProductImage)
                .where(
                    EcommerceProductImage.product_id == product.id,
                    EcommerceProductImage.deleted_at.is_(None),
                )
                .order_by(EcommerceProductImage.is_primary.desc(), EcommerceProductImage.sort_order)
                .limit(1)
            )
        ).scalar_one_or_none()
        shop = (
            await db.execute(
                select(EcommerceShop).where(
                    EcommerceShop.id == product.shop_id,
                    EcommerceShop.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        sale = EcommerceCatalogService._sale_price(product)
        return {
            "id": str(product.id),
            "name": product.name,
            "code": product.code,
            "slug": product.slug,
            "thumbnail": product.thumbnail_url,
            "thumbnail_full_url": product.thumbnail_url,
            "unit_price": float(product.unit_price),
            "discount": float(product.discount),
            "discount_type": product.discount_type.value,
            "sale_price": float(sale),
            "current_stock": product.current_stock,
            "minimum_order_qty": product.minimum_order_qty,
            "stock_status": product.stock_status.value,
            "featured": product.featured,
            "average_review": float(product.average_review),
            "reviews_count": product.reviews_count,
            "shop": {"id": str(shop.id), "name": shop.name, "slug": shop.slug} if shop else None,
            "image_url": img.url if img else product.thumbnail_url,
        }

    @staticmethod
    async def _paginate_products(db: AsyncSession, base_query, *, limit: int, offset: int) -> dict:
        count_q = select(func.count()).select_from(base_query.subquery())
        total = (await db.execute(count_q)).scalar_one()
        rows = (
            await db.execute(
                base_query.order_by(EcommerceProduct.created_at.desc())
                .offset((offset - 1) * limit)
                .limit(limit)
            )
        ).scalars().all()
        products = [await EcommerceCatalogService._product_card(db, p) for p in rows]
        prices = [p["sale_price"] for p in products]
        return {
            "total_size": total,
            "limit": limit,
            "offset": offset,
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "products": products,
        }

    @staticmethod
    async def _category_product_count(db: AsyncSession, category_id: UUID) -> int:
        return (
            await db.execute(
                select(func.count())
                .select_from(EcommerceProduct)
                .where(
                    *EcommerceCatalogService._active_filters(),
                    or_(
                        EcommerceProduct.category_id == category_id,
                        EcommerceProduct.sub_category_id == category_id,
                        EcommerceProduct.sub_sub_category_id == category_id,
                    ),
                )
            )
        ).scalar_one()

    @staticmethod
    async def _build_category_node(db: AsyncSession, cat: EcommerceCategory, all_cats: list[EcommerceCategory]) -> dict:
        children = [c for c in all_cats if c.parent_id == cat.id]
        count = await EcommerceCatalogService._category_product_count(db, cat.id)
        return {
            "id": str(cat.id),
            "name": cat.name,
            "slug": cat.slug,
            "icon": cat.icon_url,
            "icon_full_url": cat.icon_url,
            "parent_id": str(cat.parent_id) if cat.parent_id else None,
            "position": cat.position.value,
            "home_status": cat.home_status,
            "priority": cat.priority,
            "product_count": count,
            "childes": [
                await EcommerceCatalogService._build_category_node(db, child, all_cats) for child in children
            ],
        }

    @staticmethod
    async def list_categories(db: AsyncSession) -> list[dict]:
        cats = (
            await db.execute(
                select(EcommerceCategory)
                .where(EcommerceCategory.is_active.is_(True), EcommerceCategory.deleted_at.is_(None))
                .order_by(EcommerceCategory.priority.desc(), EcommerceCategory.name)
            )
        ).scalars().all()
        roots = [c for c in cats if c.position == EcommerceCategoryPosition.ROOT]
        return [await EcommerceCatalogService._build_category_node(db, root, cats) for root in roots]

    @staticmethod
    async def list_category_products(
        db: AsyncSession,
        category_id: UUID,
        *,
        limit: int = 10,
        offset: int = 1,
        search: str | None = None,
    ) -> dict:
        base = select(EcommerceProduct).where(
            *EcommerceCatalogService._active_filters(),
            or_(
                EcommerceProduct.category_id == category_id,
                EcommerceProduct.sub_category_id == category_id,
                EcommerceProduct.sub_sub_category_id == category_id,
            ),
        )
        if search:
            base = base.where(EcommerceProduct.name.ilike(f"%{search}%"))
        return await EcommerceCatalogService._paginate_products(db, base, limit=limit, offset=offset)

    @staticmethod
    async def list_latest(db: AsyncSession, *, limit: int = 10, offset: int = 1) -> dict:
        base = select(EcommerceProduct).where(*EcommerceCatalogService._active_filters())
        return await EcommerceCatalogService._paginate_products(db, base, limit=limit, offset=offset)

    @staticmethod
    async def list_featured(db: AsyncSession, *, limit: int = 10, offset: int = 1) -> dict:
        base = select(EcommerceProduct).where(
            *EcommerceCatalogService._active_filters(),
            EcommerceProduct.featured.is_(True),
        )
        return await EcommerceCatalogService._paginate_products(db, base, limit=limit, offset=offset)

    @staticmethod
    async def search_products(db: AsyncSession, *, name: str, limit: int = 10, offset: int = 1) -> dict:
        base = select(EcommerceProduct).where(
            *EcommerceCatalogService._active_filters(),
            EcommerceProduct.name.ilike(f"%{name}%"),
        )
        return await EcommerceCatalogService._paginate_products(db, base, limit=limit, offset=offset)

    @staticmethod
    async def filter_products(
        db: AsyncSession,
        *,
        search: str | None = None,
        category_ids: list[UUID] | None = None,
        brand_ids: list[UUID] | None = None,
        sort_by: str | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
        limit: int = 10,
        offset: int = 1,
    ) -> dict:
        base = select(EcommerceProduct).where(*EcommerceCatalogService._active_filters())
        if search:
            base = base.where(
                or_(
                    EcommerceProduct.name.ilike(f"%{search}%"),
                    EcommerceProduct.details.ilike(f"%{search}%"),
                )
            )
        if category_ids:
            base = base.where(
                or_(
                    EcommerceProduct.category_id.in_(category_ids),
                    EcommerceProduct.sub_category_id.in_(category_ids),
                    EcommerceProduct.sub_sub_category_id.in_(category_ids),
                )
            )
        if brand_ids:
            base = base.where(EcommerceProduct.brand_id.in_(brand_ids))
        if sort_by == "latest":
            base = base.order_by(EcommerceProduct.created_at.desc())
        elif sort_by == "a-z":
            base = base.order_by(EcommerceProduct.name.asc())
        elif sort_by == "z-a":
            base = base.order_by(EcommerceProduct.name.desc())
        elif sort_by in ("low-high", "high-low"):
            base = base.order_by(EcommerceProduct.unit_price.asc() if sort_by == "low-high" else EcommerceProduct.unit_price.desc())
        if price_min is not None:
            base = base.where(EcommerceProduct.unit_price >= price_min)
        if price_max is not None:
            base = base.where(EcommerceProduct.unit_price <= price_max)
        return await EcommerceCatalogService._paginate_products(db, base, limit=limit, offset=offset)

    @staticmethod
    async def product_detail(db: AsyncSession, slug: str) -> dict:
        product = (
            await db.execute(
                select(EcommerceProduct).where(
                    EcommerceProduct.slug == slug,
                    EcommerceProduct.deleted_at.is_(None),
                    EcommerceProduct.status == EcommerceProductStatus.PUBLISHED,
                )
            )
        ).scalar_one_or_none()
        if not product:
            raise AppError(404, "Product not found", "not_found")

        images = (
            await db.execute(
                select(EcommerceProductImage)
                .where(EcommerceProductImage.product_id == product.id, EcommerceProductImage.deleted_at.is_(None))
                .order_by(EcommerceProductImage.sort_order)
            )
        ).scalars().all()
        card = await EcommerceCatalogService._product_card(db, product)
        card.update(
            {
                "details": product.details,
                "images_full_url": [img.url for img in images],
                "category_id": str(product.category_id) if product.category_id else None,
                "sub_category_id": str(product.sub_category_id) if product.sub_category_id else None,
                "sub_sub_category_id": str(product.sub_sub_category_id) if product.sub_sub_category_id else None,
                "brand_id": str(product.brand_id) if product.brand_id else None,
            }
        )
        return card

    @staticmethod
    async def list_brands(db: AsyncSession, *, limit: int = 20, offset: int = 1) -> dict:
        total = (
            await db.execute(
                select(func.count())
                .select_from(EcommerceBrand)
                .where(EcommerceBrand.is_active.is_(True), EcommerceBrand.deleted_at.is_(None))
            )
        ).scalar_one()
        brands = (
            await db.execute(
                select(EcommerceBrand)
                .where(EcommerceBrand.is_active.is_(True), EcommerceBrand.deleted_at.is_(None))
                .order_by(EcommerceBrand.name)
                .offset((offset - 1) * limit)
                .limit(limit)
            )
        ).scalars().all()
        items = []
        for brand in brands:
            count = (
                await db.execute(
                    select(func.count())
                    .select_from(EcommerceProduct)
                    .where(
                        *EcommerceCatalogService._active_filters(),
                        EcommerceProduct.brand_id == brand.id,
                    )
                )
            ).scalar_one()
            items.append(
                {
                    "id": str(brand.id),
                    "name": brand.name,
                    "slug": brand.slug,
                    "image": brand.image_url,
                    "image_full_url": brand.image_url,
                    "brand_products_count": count,
                }
            )
        return {"total_size": total, "limit": limit, "offset": offset, "brands": items}

    @staticmethod
    async def list_brand_products(db: AsyncSession, brand_id: UUID, *, limit: int = 20, offset: int = 1) -> dict:
        base = select(EcommerceProduct).where(
            *EcommerceCatalogService._active_filters(),
            EcommerceProduct.brand_id == brand_id,
        )
        return await EcommerceCatalogService._paginate_products(db, base, limit=limit, offset=offset)

    @staticmethod
    async def list_banners(db: AsyncSession) -> list[dict]:
        banners = (
            await db.execute(
                select(EcommerceBanner)
                .where(EcommerceBanner.is_published.is_(True), EcommerceBanner.deleted_at.is_(None))
                .order_by(EcommerceBanner.sort_order)
            )
        ).scalars().all()
        result = []
        for banner in banners:
            item = {
                "id": str(banner.id),
                "photo": banner.photo_url,
                "photo_full_url": banner.photo_url,
                "title": banner.title,
                "sub_title": banner.sub_title,
                "button_text": banner.button_text,
                "background_color": banner.background_color,
                "url": banner.url,
                "resource_type": banner.resource_type.value,
                "resource_id": str(banner.resource_id) if banner.resource_id else None,
                "published": banner.is_published,
            }
            if banner.resource_type.value == "product" and banner.resource_id:
                product = (
                    await db.execute(
                        select(EcommerceProduct).where(
                            EcommerceProduct.id == banner.resource_id,
                            EcommerceProduct.deleted_at.is_(None),
                        )
                    )
                ).scalar_one_or_none()
                if product:
                    item["product"] = await EcommerceCatalogService._product_card(db, product)
            result.append(item)
        return result

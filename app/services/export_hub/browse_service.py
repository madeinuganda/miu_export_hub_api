from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.export_hub.browse_settings import ExportHubBrowseSettings
from app.models.export_hub.catalog import Category, PlatformStat, Product, ProductImage
from app.models.export_hub.organizations import SupplierOrganization
from app.models.shared.enums import ProductStatus, VerificationStatus
from app.utils.formatting import format_ugx


class BrowseService:
    @staticmethod
    async def get_settings(db: AsyncSession) -> ExportHubBrowseSettings:
        row = (
            await db.execute(
                select(ExportHubBrowseSettings)
                .where(ExportHubBrowseSettings.deleted_at.is_(None))
                .order_by(ExportHubBrowseSettings.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()
        if row:
            return row
        row = ExportHubBrowseSettings()
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def category_product_counts(db: AsyncSession) -> dict[UUID, int]:
        rows = (
            await db.execute(
                select(Product.category_id, func.count())
                .where(
                    Product.status == ProductStatus.PUBLISHED.value,
                    Product.deleted_at.is_(None),
                    Product.category_id.is_not(None),
                )
                .group_by(Product.category_id)
            )
        ).all()
        return {category_id: int(count) for category_id, count in rows if category_id}

    @staticmethod
    def _format_count(n: int) -> str:
        if n <= 0:
            return "0"
        return f"{n}+"

    @staticmethod
    async def build_categories_payload(
        db: AsyncSession,
        categories: list[Category],
        *,
        featured_only: bool = False,
    ) -> list[dict]:
        counts = await BrowseService.category_product_counts(db)
        items = []
        for cat in categories:
            if featured_only and not cat.featured:
                continue
            count = counts.get(cat.id, 0)
            items.append(
                {
                    "id": cat.slug,
                    "label": cat.label,
                    "count": BrowseService._format_count(count),
                    "featured": cat.featured,
                }
            )
        return items

    @staticmethod
    async def platform_stats_payload(db: AsyncSession) -> list[dict]:
        stats = (
            await db.execute(
                select(PlatformStat)
                .where(PlatformStat.is_active.is_(True), PlatformStat.deleted_at.is_(None))
                .order_by(PlatformStat.sort_order)
            )
        ).scalars().all()
        return [
            {"headline": s.headline, "sub": s.subtext or "", "iconKey": s.icon_key or "globe"}
            for s in stats
        ]

    @staticmethod
    async def supplier_product_stats(db: AsyncSession, org_id: UUID) -> tuple[float, int]:
        row = (
            await db.execute(
                select(
                    func.coalesce(func.avg(Product.rating), 0),
                    func.count(Product.id),
                ).where(
                    Product.supplier_org_id == org_id,
                    Product.status == ProductStatus.PUBLISHED.value,
                    Product.deleted_at.is_(None),
                )
            )
        ).one()
        return round(float(row[0] or 0), 1), int(row[1] or 0)

    @staticmethod
    async def featured_suppliers_payload(db: AsyncSession, limit: int) -> list[dict]:
        orgs = (
            await db.execute(
                select(SupplierOrganization)
                .where(
                    SupplierOrganization.featured.is_(True),
                    SupplierOrganization.verification_status == VerificationStatus.APPROVED,
                    SupplierOrganization.deleted_at.is_(None),
                )
                .order_by(SupplierOrganization.name)
                .limit(limit)
            )
        ).scalars().all()
        items = []
        for org in orgs:
            rating, product_count = await BrowseService.supplier_product_stats(db, org.id)
            tone = "coffee"
            if org.category:
                cat_lower = org.category.lower()
                if "shea" in cat_lower or "oil" in cat_lower:
                    tone = "shea"
                elif "cacao" in cat_lower or "cocoa" in cat_lower:
                    tone = "cacao"
                elif "organic" in cat_lower:
                    tone = "organic"
            items.append(
                {
                    "id": str(org.id),
                    "name": org.name,
                    "category": org.category or "Supplier",
                    "rating": rating,
                    "productCount": product_count,
                    "tone": tone,
                }
            )
        return items

    @staticmethod
    async def _product_image_url(db: AsyncSession, product_id: UUID) -> str | None:
        img = (
            await db.execute(
                select(ProductImage.url)
                .where(ProductImage.product_id == product_id, ProductImage.deleted_at.is_(None))
                .order_by(ProductImage.is_primary.desc(), ProductImage.sort_order)
                .limit(1)
            )
        ).scalar_one_or_none()
        return img

    @staticmethod
    def _deal_discount_label(price: Decimal | None, deal_price: Decimal | None) -> str | None:
        if not price or not deal_price or deal_price >= price:
            return None
        pct = int(round((1 - float(deal_price) / float(price)) * 100))
        if pct <= 0:
            return None
        return f"-{pct}%"

    @staticmethod
    async def top_deals_payload(db: AsyncSession, limit: int) -> list[dict]:
        products = (
            await db.execute(
                select(Product)
                .where(
                    Product.is_top_deal.is_(True),
                    Product.status == ProductStatus.PUBLISHED.value,
                    Product.deleted_at.is_(None),
                )
                .order_by(Product.updated_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        items = []
        for product in products:
            image = await BrowseService._product_image_url(db, product.id)
            price = product.price_amount or Decimal("0")
            deal = product.deal_price if product.deal_price is not None else price
            moq = None
            if product.moq_value:
                moq = f"MOQ: {product.moq_value:g} {product.moq_unit or 'kg'}"
            items.append(
                {
                    "id": str(product.id),
                    "name": product.name,
                    "price": format_ugx(deal, "kg"),
                    "originalPrice": format_ugx(price, "kg") if deal < price else None,
                    "unit": "/kg",
                    "moq": moq,
                    "discount": BrowseService._deal_discount_label(price, product.deal_price),
                    "tone": product.tone or "coffee",
                    "image": image,
                }
            )
        return items

    @staticmethod
    def _ranking_label(score: float, review_count: int) -> str:
        if review_count >= 50:
            return "Top Rated"
        if review_count >= 10:
            return "Highly Rated"
        return "Rising Star"

    @staticmethod
    async def top_ranking_payload(
        db: AsyncSession,
        *,
        rating_weight: Decimal,
        review_weight: Decimal,
        limit: int,
    ) -> list[dict]:
        products = (
            await db.execute(
                select(Product)
                .where(Product.status == ProductStatus.PUBLISHED.value, Product.deleted_at.is_(None))
            )
        ).scalars().all()
        rw = float(rating_weight)
        vw = float(review_weight)
        scored: list[tuple[float, Product]] = []
        for product in products:
            score = float(product.rating) * rw + product.review_count * vw
            scored.append((score, product))
        scored.sort(key=lambda item: item[0], reverse=True)
        items = []
        for _, product in scored[:limit]:
            image = await BrowseService._product_image_url(db, product.id)
            items.append(
                {
                    "id": str(product.id),
                    "name": product.name,
                    "label": BrowseService._ranking_label(float(product.rating), product.review_count),
                    "tone": product.tone or "coffee",
                    "image": image,
                    "rating": float(product.rating),
                    "reviewCount": product.review_count,
                }
            )
        return items

    @staticmethod
    async def frequently_searched_payload(db: AsyncSession, limit: int = 6) -> list[dict]:
        products = (
            await db.execute(
                select(Product)
                .where(Product.status == ProductStatus.PUBLISHED.value, Product.deleted_at.is_(None))
                .order_by(Product.review_count.desc(), Product.rating.desc())
                .limit(limit)
            )
        ).scalars().all()
        items = []
        for product in products:
            image = await BrowseService._product_image_url(db, product.id)
            items.append(
                {
                    "id": str(product.id),
                    "name": product.name,
                    "subtitle": product.subcategory,
                    "tag": "FREQUENTLY SEARCHED",
                    "tone": product.tone or "coffee",
                    "image": image,
                }
            )
        return items

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.export_hub.catalog import Category, Product, ProductBadge, ProductImage
from app.models.export_hub.marketplace import (
    CmsCategory,
    CmsFeature,
    CmsFeaturedProduct,
    CmsHero,
    CmsHowItWorksStep,
    CmsNavLink,
    CmsSiteSettings,
    CmsSupplierHero,
    CmsTestimonial,
    CmsTradeCta,
    CmsTrustItem,
)
from app.models.export_hub.catalog import PlatformStat
from app.models.shared.enums import ProductStatus
from app.utils.formatting import format_ugx


class MarketplaceService:
    @staticmethod
    async def get_public_home(db: AsyncSession) -> dict:
        hero = (await db.execute(select(CmsHero).where(CmsHero.is_active.is_(True), CmsHero.deleted_at.is_(None)).limit(1))).scalar_one_or_none()
        settings = (await db.execute(select(CmsSiteSettings).where(CmsSiteSettings.deleted_at.is_(None)).limit(1))).scalar_one_or_none()
        trust = (await db.execute(select(CmsTrustItem).where(CmsTrustItem.is_active.is_(True), CmsTrustItem.deleted_at.is_(None)).order_by(CmsTrustItem.sort_order))).scalars().all()
        cms_cats = (await db.execute(select(CmsCategory).where(CmsCategory.is_active.is_(True), CmsCategory.deleted_at.is_(None)).order_by(CmsCategory.sort_order))).scalars().all()
        featured_rows = (
            await db.execute(
                select(CmsFeaturedProduct)
                .where(CmsFeaturedProduct.is_active.is_(True), CmsFeaturedProduct.deleted_at.is_(None))
                .order_by(CmsFeaturedProduct.sort_order)
            )
        ).scalars().all()
        how = (
            await db.execute(
                select(CmsHowItWorksStep)
                .where(CmsHowItWorksStep.is_active.is_(True), CmsHowItWorksStep.deleted_at.is_(None))
                .order_by(CmsHowItWorksStep.step_number)
            )
        ).scalars().all()
        features = (
            await db.execute(
                select(CmsFeature)
                .where(CmsFeature.is_active.is_(True), CmsFeature.deleted_at.is_(None))
                .order_by(CmsFeature.sort_order)
            )
        ).scalars().all()
        testimonials = (
            await db.execute(
                select(CmsTestimonial)
                .where(CmsTestimonial.is_active.is_(True), CmsTestimonial.deleted_at.is_(None))
                .order_by(CmsTestimonial.sort_order)
            )
        ).scalars().all()
        trade_cta = (
            await db.execute(
                select(CmsTradeCta).where(CmsTradeCta.is_active.is_(True), CmsTradeCta.deleted_at.is_(None)).limit(1)
            )
        ).scalar_one_or_none()
        supplier_hero = (
            await db.execute(
                select(CmsSupplierHero).where(CmsSupplierHero.is_active.is_(True), CmsSupplierHero.deleted_at.is_(None)).limit(1)
            )
        ).scalar_one_or_none()
        nav = (
            await db.execute(
                select(CmsNavLink)
                .where(CmsNavLink.is_active.is_(True), CmsNavLink.deleted_at.is_(None))
                .order_by(CmsNavLink.sort_order)
            )
        ).scalars().all()
        stats = (
            await db.execute(
                select(PlatformStat)
                .where(PlatformStat.is_active.is_(True), PlatformStat.deleted_at.is_(None))
                .order_by(PlatformStat.sort_order)
            )
        ).scalars().all()
        categories = (
            await db.execute(
                select(Category).where(Category.is_active.is_(True), Category.deleted_at.is_(None)).order_by(Category.sort_order)
            )
        ).scalars().all()

        featured_products = []
        for row in featured_rows:
            if row.snapshot:
                featured_products.append(row.snapshot)
            elif row.product_id:
                p = await db.get(Product, row.product_id)
                if p and p.deleted_at is None:
                    featured_products.append(await MarketplaceService._product_card(db, p))

        return {
            "announcement": settings.announcement_text if settings else None,
            "hero": MarketplaceService._hero(hero),
            "trust": [{"icon": t.icon, "title": t.title, "body": t.body} for t in trust],
            "categories": [{"id": str(c.id), "slug": c.slug, "label": c.label} for c in categories],
            "cmsCategories": [{"title": c.title, "imageUrl": c.image_url, "copy": c.copy_text} for c in cms_cats],
            "featuredProducts": featured_products,
            "howItWorks": [{"step": h.step_number, "title": h.title, "body": h.body, "icon": h.icon} for h in how],
            "stats": [{"key": s.key, "headline": s.headline, "subtext": s.subtext, "iconKey": s.icon_key} for s in stats],
            "features": [{"title": f.title, "body": f.body, "icon": f.icon} for f in features],
            "testimonials": [
                {
                    "quote": t.quote,
                    "author": t.author,
                    "role": t.role,
                    "company": t.company,
                    "country": t.country,
                    "avatarUrl": t.avatar_url,
                }
                for t in testimonials
            ],
            "tradeCta": {
                "title": trade_cta.title,
                "body": trade_cta.body,
                "buttonLabel": trade_cta.button_label,
                "buttonUrl": trade_cta.button_url,
            }
            if trade_cta
            else None,
            "supplierHero": {
                "title": supplier_hero.title,
                "body": supplier_hero.body,
                "ctaLabel": supplier_hero.cta_label,
                "ctaUrl": supplier_hero.cta_url,
            }
            if supplier_hero
            else None,
            "nav": [{"label": n.label, "href": n.href} for n in nav],
            "siteSettings": {
                "phone": settings.phone if settings else None,
                "email": settings.email if settings else None,
                "footerLinks": settings.footer_links if settings else [],
            },
        }

    @staticmethod
    def _hero(hero: CmsHero | None) -> dict | None:
        if not hero:
            return None
        return {
            "eyebrow": hero.eyebrow,
            "title": hero.title,
            "subtitle": hero.subtitle,
            "ctaPrimary": {"label": hero.cta_primary_label, "url": hero.cta_primary_url},
            "ctaSecondary": {"label": hero.cta_secondary_label, "url": hero.cta_secondary_url},
            "backgroundImageUrl": hero.background_image_url,
        }

    @staticmethod
    async def _product_card(db: AsyncSession, product: Product) -> dict:
        img = (
            await db.execute(
                select(ProductImage)
                .where(ProductImage.product_id == product.id, ProductImage.deleted_at.is_(None))
                .order_by(ProductImage.is_primary.desc(), ProductImage.sort_order)
                .limit(1)
            )
        ).scalar_one_or_none()
        badges = (
            await db.execute(select(ProductBadge.badge).where(ProductBadge.product_id == product.id, ProductBadge.deleted_at.is_(None)))
        ).scalars().all()
        badge = badges[0] if badges else None
        return {
            "id": str(product.id),
            "category": product.subcategory or "PRODUCT",
            "title": product.name,
            "rating": float(product.rating),
            "reviews": product.review_count,
            "price": format_ugx(product.price_amount or 0),
            "unit": "per kg",
            "moq": f"{product.moq_value:g} {product.moq_unit} MOQ" if product.moq_value else "",
            "seller": "via MIU",
            "location": "Uganda",
            "badge": badge,
            "imageUrl": img.url if img else "",
        }

    @staticmethod
    async def get_featured_products(db: AsyncSession) -> list[dict]:
        result = await db.execute(
            select(Product).where(Product.status == ProductStatus.PUBLISHED.value, Product.deleted_at.is_(None)).limit(12)
        )
        products = result.scalars().all()
        return [await MarketplaceService._product_card(db, p) for p in products]

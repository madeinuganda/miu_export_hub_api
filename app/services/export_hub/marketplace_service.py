from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.export_hub.catalog import Category, Product, ProductBadge, ProductImage
from app.models.export_hub.organizations import SupplierOrganization
from app.models.shared.enums import VerificationStatus
from app.models.export_hub.marketplace import (
    CmsCategory,
    CmsFeature,
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
from app.services.export_hub.testimonial_service import TestimonialService
from app.utils.formatting import format_ugx


class MarketplaceService:
    @staticmethod
    async def get_public_home(db: AsyncSession) -> dict:
        hero = (await db.execute(select(CmsHero).where(CmsHero.is_active.is_(True), CmsHero.deleted_at.is_(None)).limit(1))).scalar_one_or_none()
        settings = (await db.execute(select(CmsSiteSettings).where(CmsSiteSettings.deleted_at.is_(None)).limit(1))).scalar_one_or_none()
        trust = (await db.execute(select(CmsTrustItem).where(CmsTrustItem.is_active.is_(True), CmsTrustItem.deleted_at.is_(None)).order_by(CmsTrustItem.sort_order))).scalars().all()
        cms_cats = (await db.execute(select(CmsCategory).where(CmsCategory.is_active.is_(True), CmsCategory.deleted_at.is_(None)).order_by(CmsCategory.sort_order))).scalars().all()
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
        public_categories = await MarketplaceService._public_categories(db, categories)

        featured_products = await MarketplaceService.get_featured_products(db)

        return {
            "announcement": settings.announcement_text if settings else None,
            "hero": MarketplaceService._hero(hero),
            "trust": [{"icon": t.icon, "title": t.title, "body": t.body} for t in trust],
            "categories": public_categories,
            "cmsCategories": [{"title": c.title, "imageUrl": c.image_url, "copy": c.copy_text} for c in cms_cats],
            "featuredProducts": featured_products,
            "howItWorks": [{"step": h.step_number, "title": h.title, "body": h.body, "icon": h.icon} for h in how],
            "stats": [{"key": s.key, "headline": s.headline, "subtext": s.subtext, "iconKey": s.icon_key} for s in stats],
            "features": [{"title": f.title, "body": f.body, "icon": f.icon} for f in features],
            "testimonials": [
                TestimonialService._to_public_item(t).model_dump()
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
    async def _public_categories(db: AsyncSession, categories: list[Category]) -> list[dict]:
        if not categories:
            return []

        counts_rows = (
            await db.execute(
                select(Product.category_id, func.count())
                .where(
                    Product.deleted_at.is_(None),
                    Product.category_id.is_not(None),
                )
                .group_by(Product.category_id)
            )
        ).all()
        counts = {row[0]: int(row[1]) for row in counts_rows}

        return [
            {
                "id": str(c.id),
                "slug": c.slug,
                "label": c.label,
                "description": c.description or "",
                "thumbUrl": c.thumb_url or "",
                "imageUrl": c.image_url or "",
                "productCount": counts.get(c.id, 0),
            }
            for c in categories
        ]

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
    def _supplier_location(org: SupplierOrganization | None) -> str:
        if not org:
            return "Uganda"
        city = org.district or org.region
        return f"{city}, UG" if city else "Uganda"

    @staticmethod
    def _category_label(product: Product, category: Category | None) -> str:
        label = category.label if category else (product.subcategory or "Product")
        return label.upper()

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
            await db.execute(
                select(ProductBadge.badge).where(
                    ProductBadge.product_id == product.id,
                    ProductBadge.deleted_at.is_(None),
                )
            )
        ).scalars().all()

        category = await db.get(Category, product.category_id) if product.category_id else None
        org = await db.get(SupplierOrganization, product.supplier_org_id)
        supplier_verified = bool(org and org.verification_status == VerificationStatus.APPROVED)
        badge = badges[0] if badges else ("verified" if supplier_verified else None)

        unit = product.moq_unit or "kg"
        rating = min(5, max(0, round(float(product.rating))))
        seller = org.name if org else "MIU Supplier"
        location = MarketplaceService._supplier_location(org)

        return {
            "id": str(product.id),
            "category": MarketplaceService._category_label(product, category),
            "title": product.name,
            "rating": rating,
            "reviews": product.review_count,
            "price": format_ugx(product.price_amount or 0),
            "currency": product.price_currency or "UGX",
            "unit": f"per {unit}",
            "moq": f"{product.moq_value:g} {unit} MOQ" if product.moq_value else "",
            "seller": seller,
            "supplierInitials": seller[:1].upper() if seller else "M",
            "location": location,
            "badge": badge,
            "isVerified": badge == "verified" or supplier_verified,
            "imageUrl": img.url if img else "",
        }

    @staticmethod
    async def get_featured_products(db: AsyncSession, *, limit: int = 12) -> list[dict]:
        result = await db.execute(
            select(Product)
            .where(
                Product.featured.is_(True),
                Product.status == ProductStatus.PUBLISHED,
                Product.deleted_at.is_(None),
            )
            .order_by(Product.updated_at.desc())
            .limit(limit)
        )
        products = result.scalars().all()
        return [await MarketplaceService._product_card(db, p) for p in products]

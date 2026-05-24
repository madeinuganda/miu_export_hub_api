from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Category, Product, ProductBadge, ProductCertification, ProductImage
from app.models.enums import ProductStatus
from app.models.organizations import SupplierOrganization
from app.utils.formatting import format_quantity, format_ugx


ANONYMIZED_SUPPLIER = "via MIU"


class CatalogService:
    @staticmethod
    async def buyer_browse(db: AsyncSession, category_id: UUID | None = None, q: str | None = None) -> dict:
        cats = (
            await db.execute(select(Category).where(Category.is_active.is_(True), Category.deleted_at.is_(None)).order_by(Category.sort_order))
        ).scalars().all()
        query = select(Product).where(Product.status == ProductStatus.PUBLISHED, Product.deleted_at.is_(None))
        if category_id:
            query = query.where(Product.category_id == category_id)
        if q:
            query = query.where(or_(Product.name.ilike(f"%{q}%"), Product.description.ilike(f"%{q}%")))
        products = (await db.execute(query.limit(50))).scalars().all()
        return {
            "categories": [{"id": c.slug, "label": c.label, "count": "24+"} for c in cats],
            "frequentlySearched": ["Coffee", "Vanilla", "Shea Butter"],
            "stats": [],
            "featuredSuppliers": [],
            "topDeals": [],
            "topRanking": [],
            "products": [await CatalogService._buyer_listing(db, p, mask_supplier=True) for p in products],
        }

    @staticmethod
    async def _buyer_listing(db: AsyncSession, product: Product, mask_supplier: bool = True) -> dict:
        img = (
            await db.execute(
                select(ProductImage)
                .where(ProductImage.product_id == product.id, ProductImage.deleted_at.is_(None))
                .order_by(ProductImage.is_primary.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        certs = (
            await db.execute(
                select(ProductCertification.certification_name).where(
                    ProductCertification.product_id == product.id,
                    ProductCertification.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        badges = (
            await db.execute(
                select(ProductBadge.badge).where(
                    ProductBadge.product_id == product.id,
                    ProductBadge.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        category_slug = "all"
        if product.category_id:
            cat = await db.get(Category, product.category_id)
            if cat:
                category_slug = cat.slug

        org = await db.get(SupplierOrganization, product.supplier_org_id)
        supplier_name = ANONYMIZED_SUPPLIER
        if not mask_supplier and org:
            location = org.district or org.region or "Uganda"
            supplier_name = f"{org.name} · {location}"
        elif org and (org.district or org.region):
            supplier_name = f"{ANONYMIZED_SUPPLIER} · {org.district or org.region}"

        moq = None
        if product.moq_value:
            unit = product.moq_unit or "kg"
            moq = f"MOQ: {product.moq_value:g} {unit}"
        lead = f"Lead: {product.lead_time_days} days" if product.lead_time_days else None

        badge_list = list(badges) if badges else ["verified"]

        return {
            "id": str(product.id),
            "name": product.name,
            "subtitle": product.subcategory,
            "image": img.url if img else None,
            "price": format_ugx(product.price_amount or 0, "kg"),
            "moq": moq,
            "lead": lead,
            "unit": "kg",
            "tone": product.tone or "coffee",
            "supplierName": supplier_name,
            "supplier": supplier_name,
            "rating": float(product.rating),
            "reviewCount": product.review_count,
            "badges": badge_list,
            "certs": list(certs),
            "categoryId": category_slug,
            "category": product.subcategory,
            "sampleAvailable": product.sample_available,
        }

    @staticmethod
    async def buyer_product_detail(db: AsyncSession, product_id: UUID, reveal_supplier: bool = False) -> dict:
        product = await db.get(Product, product_id)
        if not product or product.deleted_at or product.status != ProductStatus.PUBLISHED:
            from app.core.exceptions import AppError
            raise AppError(404, "Product not found", "not_found")
        listing = await CatalogService._buyer_listing(db, product, mask_supplier=not reveal_supplier)
        images = (
            await db.execute(
                select(ProductImage.url)
                .where(ProductImage.product_id == product.id, ProductImage.deleted_at.is_(None))
                .order_by(ProductImage.sort_order)
            )
        ).scalars().all()
        org = await db.get(SupplierOrganization, product.supplier_org_id)
        return {
            **listing,
            "shortDescription": product.description or "",
            "originStory": product.origin_story or "",
            "images": list(images) or ([listing.get("image")] if listing.get("image") else []),
            "categoryLabel": product.subcategory or "",
            "stock": format_quantity(product.moq_value or Decimal("0"), product.moq_unit or "kg"),
            "tradeAssurance": product.trade_assurance_note or "70% upfront",
            "sampleAvailable": product.sample_available,
            "supplierInitial": (org.name[0] if org and reveal_supplier else "M"),
            "supplierLocation": f"{org.district or org.region}, Uganda" if org else "Uganda",
            "supplierResponseTime": "< 2 hours",
        }

    @staticmethod
    async def supplier_products(db: AsyncSession, org_id: UUID, q: str | None = None) -> dict:
        query = select(Product).where(Product.supplier_org_id == org_id, Product.deleted_at.is_(None))
        if q:
            query = query.where(Product.name.ilike(f"%{q}%"))
        products = (await db.execute(query.order_by(Product.updated_at.desc()))).scalars().all()
        rows = []
        for p in products:
            certs = (
                await db.execute(
                    select(ProductCertification.certification_name).where(
                        ProductCertification.product_id == p.id, ProductCertification.deleted_at.is_(None)
                    )
                )
            ).scalars().all()
            stock_map = {"in_stock": "In Stock", "low_stock": "Low Stock", "out_of_stock": "Out of Stock"}
            rows.append(
                {
                    "id": str(p.id),
                    "sku": p.sku,
                    "name": p.name,
                    "category": p.subcategory or "",
                    "moq": f"{p.moq_value:g} {p.moq_unit} min" if p.moq_value else "",
                    "price": format_ugx(p.price_amount or 0, "kg"),
                    "certifications": list(certs),
                    "stockStatus": stock_map.get(p.stock_status.value, "In Stock"),
                    "status": p.status.value,
                    "thumbTone": p.tone or "coffee",
                }
            )
        published = sum(1 for r in rows if r["status"] == "published")
        return {"summary": {"total": len(rows), "published": published, "storefrontPublished": published}, "items": rows}

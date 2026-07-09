from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.models.export_hub.catalog import Category, Product, ProductBadge, ProductCertification, ProductImage
from app.models.shared.enums import ProductStatus
from app.models.export_hub.organizations import SupplierOrganization
from app.services.export_hub.browse_service import BrowseService
from app.services.shared.file_storage import public_file_url, store_upload_bytes
from app.utils.audit import apply_create_audit, apply_update_audit, soft_delete
from app.utils.formatting import format_quantity, format_ugx


ANONYMIZED_SUPPLIER = "via MIU"
SHOP_CATEGORY_SECTION_FALLBACKS: list[tuple[str, str]] = [
    ("packaged-foods", "Packaged Foods"),
    ("beverages", "Beverages"),
    ("snacks", "Snacks"),
    ("home-care", "Home Care"),
    ("personal-care", "Personal Care"),
    ("household", "Household Essentials"),
]


class CatalogService:
    @staticmethod
    def _is_shop_customer(customer_type: str | None) -> bool:
        normalized = (customer_type or "").strip().lower()
        return normalized in {"shop", "retail", "retailer"}

    @staticmethod
    def _with_shop_category_sections(categories: list[Category], existing: list[dict]) -> list[dict]:
        items = list(existing)
        existing_ids = {item["id"] for item in items}
        for section_id, label in SHOP_CATEGORY_SECTION_FALLBACKS:
            if section_id in existing_ids:
                continue
            items.append({"id": section_id, "label": label, "count": "0", "featured": False})
        return items

    @staticmethod
    async def buyer_browse(
        db: AsyncSession,
        category_id: UUID | None = None,
        category_slug: str | None = None,
        q: str | None = None,
        customer_type: str | None = None,
    ) -> dict:
        settings = await BrowseService.get_settings(db)
        cats = (
            await db.execute(
                select(Category)
                .where(Category.is_active.is_(True), Category.deleted_at.is_(None))
                .order_by(Category.sort_order, Category.label)
            )
        ).scalars().all()

        resolved_category_id = category_id
        if category_slug and category_slug.strip().lower() not in {"", "all"}:
            match = next((c for c in cats if c.slug == category_slug.strip()), None)
            if match:
                resolved_category_id = match.id

        query = select(Product).where(
            Product.status == ProductStatus.PUBLISHED.value,
            Product.deleted_at.is_(None),
        )
        if resolved_category_id:
            query = query.where(Product.category_id == resolved_category_id)
        if q:
            query = query.where(
                or_(Product.name.ilike(f"%{q}%"), Product.description.ilike(f"%{q}%"))
            )
        products = (
            await db.execute(query.order_by(Product.updated_at.desc()).limit(50))
        ).scalars().all()

        categories_payload = await BrowseService.build_categories_payload(db, cats)
        if CatalogService._is_shop_customer(customer_type):
            categories_payload = CatalogService._with_shop_category_sections(cats, categories_payload)

        featured_categories = (
            await BrowseService.build_categories_payload(db, cats, featured_only=True)
        )[: settings.featured_categories_limit]

        return {
            "categories": categories_payload,
            "featuredCategories": featured_categories,
            "frequentlySearched": await BrowseService.frequently_searched_payload(db),
            "stats": await BrowseService.platform_stats_payload(db),
            "featuredSuppliers": await BrowseService.featured_suppliers_payload(
                db, settings.featured_suppliers_limit
            ),
            "topDeals": await BrowseService.top_deals_payload(db, settings.top_deals_limit),
            "topRanking": await BrowseService.top_ranking_payload(
                db,
                rating_weight=settings.ranking_rating_weight,
                review_weight=settings.ranking_review_weight,
                limit=settings.top_ranking_limit,
            ),
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
            from app.core.shared.exceptions import AppError
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
            stock_map = {
                "in_stock": "In Stock",
                "low_stock": "Made to Order",
                "out_of_stock": "Out of Stock",
            }
            image_url = await BrowseService._product_image_url(db, p.id)
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
                    "imageUrl": image_url,
                }
            )
        published = sum(1 for r in rows if r["status"] == "published")
        return {"summary": {"total": len(rows), "published": published, "storefrontPublished": published}, "items": rows}

    @staticmethod
    async def supplier_product_detail(db: AsyncSession, org_id: UUID, product_id: UUID) -> dict:
        from app.core.shared.exceptions import AppError

        product = await db.get(Product, product_id)
        if not product or product.deleted_at or product.supplier_org_id != org_id:
            raise AppError(404, "Product not found", "not_found")

        listing = await CatalogService._buyer_listing(db, product, mask_supplier=False)
        images = (
            await db.execute(
                select(ProductImage.url)
                .where(ProductImage.product_id == product.id, ProductImage.deleted_at.is_(None))
                .order_by(ProductImage.is_primary.desc(), ProductImage.sort_order)
            )
        ).scalars().all()
        certs = (
            await db.execute(
                select(ProductCertification.certification_name).where(
                    ProductCertification.product_id == product.id,
                    ProductCertification.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        org = await db.get(SupplierOrganization, product.supplier_org_id)
        category_label = product.subcategory or ""
        if product.category_id:
            cat = await db.get(Category, product.category_id)
            if cat:
                category_label = cat.label

        return {
            **listing,
            "sku": product.sku,
            "status": product.status.value,
            "shortDescription": product.description or "",
            "originStory": product.origin_story or "",
            "images": list(images) or ([listing.get("image")] if listing.get("image") else []),
            "categoryLabel": category_label,
            "categoryId": str(product.category_id) if product.category_id else None,
            "moqValue": float(product.moq_value) if product.moq_value is not None else None,
            "moqUnit": product.moq_unit or "kg",
            "priceAmount": float(product.price_amount) if product.price_amount is not None else None,
            "priceCurrency": product.price_currency or "UGX",
            "leadTimeDays": product.lead_time_days,
            "stockStatus": product.stock_status.value,
            "tradeAssurance": product.trade_assurance_note or "70% upfront",
            "sampleAvailable": product.sample_available,
            "certifications": list(certs),
            "certs": list(certs),
            "supplierInitial": org.name[0] if org else "M",
            "supplierLocation": (
                f"{org.district or org.region}, Uganda" if org and (org.district or org.region) else "Uganda"
            ),
            "supplierResponseTime": "< 2 hours",
            "tone": product.tone or "coffee",
        }

    @staticmethod
    async def update_supplier_product(
        db: AsyncSession,
        org_id: UUID,
        account_id: UUID,
        product_id: UUID,
        data: dict,
    ) -> dict:
        from decimal import Decimal

        from app.core.shared.exceptions import AppError
        from app.utils.audit import apply_update_audit

        product = await db.get(Product, product_id)
        if not product or product.deleted_at or product.supplier_org_id != org_id:
            raise AppError(404, "Product not found", "not_found")

        if "name" in data and data["name"]:
            product.name = str(data["name"]).strip()
        if "description" in data:
            product.description = data.get("description")
        if "originStory" in data or "origin_story" in data:
            product.origin_story = data.get("originStory") or data.get("origin_story")
        if "sku" in data and data["sku"]:
            product.sku = str(data["sku"]).strip()

        raw_category_id = data.get("categoryId") or data.get("category_id")
        category_label = data.get("category")
        if raw_category_id:
            try:
                resolved_category_id = UUID(str(raw_category_id))
            except ValueError as exc:
                raise AppError(400, "Invalid category id", "validation_error") from exc
            cat = await db.get(Category, resolved_category_id)
            if not cat or cat.deleted_at or not cat.is_active:
                raise AppError(400, "Category not found or inactive", "invalid_category")
            product.category_id = resolved_category_id
            product.subcategory = cat.label
        elif category_label is not None:
            product.subcategory = str(category_label)

        if "status" in data and data["status"] is not None:
            status_raw = str(data["status"]).lower()
            product.status = ProductStatus.DRAFT if status_raw == "draft" else ProductStatus.PUBLISHED

        if "moqValue" in data and data["moqValue"] is not None:
            product.moq_value = Decimal(str(data["moqValue"]))
        if "moqUnit" in data and data["moqUnit"]:
            product.moq_unit = str(data["moqUnit"])
        if "priceAmount" in data and data["priceAmount"] is not None:
            product.price_amount = Decimal(str(data["priceAmount"]))
        if "leadTimeDays" in data:
            product.lead_time_days = int(data["leadTimeDays"]) if data["leadTimeDays"] is not None else None
        if "tone" in data and data["tone"]:
            product.tone = str(data["tone"])
        if "tradeAssurance" in data or "trade_assurance_note" in data:
            product.trade_assurance_note = data.get("tradeAssurance") or data.get("trade_assurance_note")
        if "sampleAvailable" in data or "sample_available" in data:
            raw = data.get("sampleAvailable") if "sampleAvailable" in data else data.get("sample_available")
            product.sample_available = bool(raw)

        certs = data.get("certifications") or data.get("certs")
        if certs is not None:
            existing = (
                await db.execute(
                    select(ProductCertification).where(
                        ProductCertification.product_id == product.id,
                        ProductCertification.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
            for row in existing:
                soft_delete(row, account_id)
            for name in certs:
                label = str(name).strip()
                if not label:
                    continue
                cert = ProductCertification(product_id=product.id, certification_name=label)
                apply_create_audit(cert, account_id)
                db.add(cert)

        apply_update_audit(product, account_id)
        await db.flush()
        return await CatalogService.supplier_product_detail(db, org_id, product_id)

    @staticmethod
    async def upload_product_image(
        db: AsyncSession,
        org_id: UUID,
        account_id: UUID,
        product_id: UUID,
        file: UploadFile,
        *,
        is_primary: bool = False,
        sort_order: int = 0,
    ) -> str:
        product = await db.get(Product, product_id)
        if not product or product.deleted_at or product.supplier_org_id != org_id:
            raise AppError(404, "Product not found", "not_found")

        content = await file.read()
        if not content:
            raise AppError(400, "Empty file", "empty_file")

        settings = get_settings()
        mime = file.content_type or "image/jpeg"
        suffix = Path(file.filename or "product.jpg").suffix.lower() or ".jpg"
        if mime not in settings.mime_allowlist:
            raise AppError(400, f"File type not allowed: {mime}", "invalid_mime")

        record = await store_upload_bytes(
            db,
            content=content,
            mime_type=mime,
            suffix=suffix,
            uploaded_by=account_id,
            subdirectory=f"products/{product.id}",
        )
        url = public_file_url(record.storage_key)

        if is_primary:
            existing_images = (
                await db.execute(
                    select(ProductImage).where(
                        ProductImage.product_id == product.id,
                        ProductImage.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
            for row in existing_images:
                row.is_primary = False

        image = ProductImage(
            product_id=product.id,
            url=url,
            is_primary=is_primary,
            sort_order=sort_order,
        )
        apply_create_audit(image, account_id)
        db.add(image)
        apply_update_audit(product, account_id)
        await db.flush()
        return url

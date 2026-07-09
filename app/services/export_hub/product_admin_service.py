from __future__ import annotations

import math
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.models.export_hub.accounts import AdminAccount
from app.models.export_hub.catalog import Category, Product, ProductImage
from app.models.export_hub.organizations import SupplierOrganization
from app.models.shared.enums import ProductStatus
from app.schemas.export_hub.admin import AdminProductFeaturedUpdate, AdminProductListItem, AdminProductListResponse
from app.utils.audit import apply_update_audit
from app.utils.formatting import format_ugx


class ProductAdminService:
    @staticmethod
    async def _primary_image(db: AsyncSession, product_id: UUID) -> str | None:
        img = (
            await db.execute(
                select(ProductImage)
                .where(ProductImage.product_id == product_id, ProductImage.deleted_at.is_(None))
                .order_by(ProductImage.is_primary.desc(), ProductImage.sort_order)
                .limit(1)
            )
        ).scalar_one_or_none()
        return img.url if img else None

    @staticmethod
    async def _to_item(db: AsyncSession, product: Product) -> AdminProductListItem:
        org = await db.get(SupplierOrganization, product.supplier_org_id)
        category_label = product.subcategory
        if product.category_id:
            cat = await db.get(Category, product.category_id)
            if cat:
                category_label = cat.label

        return AdminProductListItem(
            id=product.id,
            sku=product.sku,
            name=product.name,
            supplier_name=org.name if org else "Unknown supplier",
            supplier_org_id=product.supplier_org_id,
            category=category_label,
            status=product.status.value,
            featured=product.featured,
            price_display=format_ugx(product.price_amount or 0),
            image_url=await ProductAdminService._primary_image(db, product.id),
            updated_at=product.updated_at,
        )

    @staticmethod
    async def list_products(
        db: AsyncSession,
        *,
        q: str | None = None,
        status: str | None = None,
        featured: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AdminProductListResponse:
        query = select(Product).where(Product.deleted_at.is_(None))
        count_query = select(func.count()).select_from(Product).where(Product.deleted_at.is_(None))

        if q:
            pattern = f"%{q.strip()}%"
            filter_expr = or_(Product.name.ilike(pattern), Product.sku.ilike(pattern))
            query = query.where(filter_expr)
            count_query = count_query.where(filter_expr)

        if status:
            try:
                status_enum = ProductStatus(status)
            except ValueError as exc:
                raise AppError(400, "Invalid product status", "invalid_status") from exc
            query = query.where(Product.status == status_enum)
            count_query = count_query.where(Product.status == status_enum)

        if featured is not None:
            query = query.where(Product.featured.is_(featured))
            count_query = count_query.where(Product.featured.is_(featured))

        total = int((await db.execute(count_query)).scalar() or 0)
        featured_count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Product)
                    .where(Product.deleted_at.is_(None), Product.featured.is_(True))
                )
            ).scalar()
            or 0
        )
        pages = max(1, math.ceil(total / page_size)) if total else 1
        offset = (page - 1) * page_size

        products = (
            await db.execute(
                query.order_by(Product.featured.desc(), Product.updated_at.desc()).offset(offset).limit(page_size)
            )
        ).scalars().all()

        items = [await ProductAdminService._to_item(db, product) for product in products]
        return AdminProductListResponse(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            pages=pages,
            featured_count=featured_count,
        )

    @staticmethod
    async def set_featured(
        db: AsyncSession,
        admin: AdminAccount,
        product_id: UUID,
        data: AdminProductFeaturedUpdate,
    ) -> AdminProductListItem:
        product = await db.get(Product, product_id)
        if not product or product.deleted_at:
            raise AppError(404, "Product not found", "not_found")

        if data.featured and product.status != ProductStatus.PUBLISHED:
            raise AppError(
                400,
                "Only published products can be featured on the marketplace",
                "product_not_published",
            )

        product.featured = data.featured
        apply_update_audit(product, admin.id)
        await db.flush()
        await db.refresh(product)
        return await ProductAdminService._to_item(db, product)

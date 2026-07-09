from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.models.export_hub.accounts import SupplierAccount
from app.models.export_hub.catalog import Product
from app.models.export_hub.orders import Order
from app.models.export_hub.organizations import (
    SupplierCertification,
    SupplierGalleryPhoto,
    SupplierOrganization,
)
from app.models.export_hub.rfqs import Rfq
from app.models.shared.enums import CertificationStatus, OrderStatus, ProductStatus, VerificationStatus
from app.schemas.export_hub.storefront import (
    CertificationCreate,
    CertificationUpdate,
    GalleryPhotoCreate,
    GalleryPhotoUpdate,
    StorefrontCertificationItem,
    StorefrontCompanyDetails,
    StorefrontFeaturedProduct,
    StorefrontGalleryItem,
    StorefrontResponse,
    StorefrontStatItem,
    StorefrontUpdate,
)
from app.services.shared.file_storage import public_file_url, store_upload_bytes
from app.utils.audit import apply_create_audit, apply_update_audit, soft_delete
from app.utils.formatting import format_ugx


class StorefrontService:
    LIVE_LABEL = "Storefront Live — visible to verified international buyers"

    @staticmethod
    def _format_location(org: SupplierOrganization) -> str:
        parts = [p for p in (org.district, org.region) if p]
        location = ", ".join(parts) if parts else "Uganda"
        if parts and "Uganda" not in location:
            location = f"{location}, Uganda"
        return location

    @staticmethod
    def _public_url(org: SupplierOrganization) -> str:
        return f"miu.ug/s/{org.slug}"

    @staticmethod
    def _cert_tone(status: CertificationStatus) -> str:
        if status == CertificationStatus.VERIFIED:
            return "verified"
        if status == CertificationStatus.EXPIRED:
            return "expired"
        return "pending"

    @staticmethod
    def _is_live(org: SupplierOrganization) -> bool:
        return (
            org.verification_status == VerificationStatus.APPROVED
            and org.storefront_published
            and org.deleted_at is None
        )

    @staticmethod
    async def _stats(db: AsyncSession, org_id: UUID) -> list[StorefrontStatItem]:
        active_products = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Product)
                    .where(
                        Product.supplier_org_id == org_id,
                        Product.status == ProductStatus.PUBLISHED,
                        Product.deleted_at.is_(None),
                    )
                )
            ).scalar()
            or 0
        )
        fulfilled_orders = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Order)
                    .where(
                        Order.supplier_org_id == org_id,
                        Order.status == OrderStatus.FULFILLED,
                        Order.deleted_at.is_(None),
                    )
                )
            ).scalar()
            or 0
        )
        avg_rating_row = (
            await db.execute(
                select(func.avg(Product.rating))
                .where(
                    Product.supplier_org_id == org_id,
                    Product.status == ProductStatus.PUBLISHED,
                    Product.deleted_at.is_(None),
                )
            )
        ).scalar()
        avg_rating = float(avg_rating_row or 0)
        avg_rating_display = f"{avg_rating:.1f}" if avg_rating else "0.0"

        buyer_counts = (
            await db.execute(
                select(Order.buyer_org_id, func.count())
                .where(Order.supplier_org_id == org_id, Order.deleted_at.is_(None))
                .group_by(Order.buyer_org_id)
            )
        ).all()
        repeat_buyers = sum(1 for _, count in buyer_counts if int(count or 0) > 1)

        return [
            StorefrontStatItem(id="products", label="Active Products", value=str(active_products)),
            StorefrontStatItem(id="orders", label="Orders Fulfilled", value=str(fulfilled_orders)),
            StorefrontStatItem(id="rating", label="Avg. Rating", value=avg_rating_display),
            StorefrontStatItem(id="buyers", label="Repeat Buyers", value=str(repeat_buyers)),
        ]

    @staticmethod
    async def _featured_products(db: AsyncSession, org_id: UUID) -> list[StorefrontFeaturedProduct]:
        products = (
            await db.execute(
                select(Product)
                .where(
                    Product.supplier_org_id == org_id,
                    Product.status == ProductStatus.PUBLISHED,
                    Product.deleted_at.is_(None),
                )
                .order_by(Product.featured.desc(), Product.rating.desc(), Product.updated_at.desc())
                .limit(4)
            )
        ).scalars().all()

        items: list[StorefrontFeaturedProduct] = []
        for product in products:
            inquiries = int(
                (
                    await db.execute(
                        select(func.count())
                        .select_from(Rfq)
                        .where(Rfq.product_id == product.id, Rfq.deleted_at.is_(None))
                    )
                ).scalar()
                or 0
            )
            moq = (
                f"MOQ: {product.moq_value:g} {product.moq_unit}"
                if product.moq_value
                else "MOQ: —"
            )
            items.append(
                StorefrontFeaturedProduct(
                    id=str(product.id),
                    name=product.name,
                    price=format_ugx(product.price_amount or 0, "kg"),
                    moq=moq,
                    rating=float(product.rating or 0),
                    inquiries=inquiries,
                    thumbTone=product.tone or "coffee",
                    featured=bool(product.featured),
                )
            )
        return items

    @staticmethod
    async def _certifications(db: AsyncSession, org_id: UUID) -> list[StorefrontCertificationItem]:
        rows = (
            await db.execute(
                select(SupplierCertification)
                .where(
                    SupplierCertification.org_id == org_id,
                    SupplierCertification.deleted_at.is_(None),
                )
                .order_by(SupplierCertification.sort_order, SupplierCertification.created_at)
            )
        ).scalars().all()
        return [
            StorefrontCertificationItem(
                id=row.id,
                name=row.name,
                status=row.status.value,
                tone=StorefrontService._cert_tone(row.status),
                expiryDate=row.expiry_date,
                sortOrder=row.sort_order,
            )
            for row in rows
        ]

    @staticmethod
    async def _gallery(db: AsyncSession, org_id: UUID) -> list[StorefrontGalleryItem]:
        rows = (
            await db.execute(
                select(SupplierGalleryPhoto)
                .where(
                    SupplierGalleryPhoto.org_id == org_id,
                    SupplierGalleryPhoto.deleted_at.is_(None),
                )
                .order_by(SupplierGalleryPhoto.sort_order, SupplierGalleryPhoto.created_at)
            )
        ).scalars().all()
        return [
            StorefrontGalleryItem(
                id=row.id,
                imageUrl=row.image_url,
                caption=row.caption,
                sortOrder=row.sort_order,
            )
            for row in rows
        ]

    @staticmethod
    async def get_storefront(db: AsyncSession, org: SupplierOrganization) -> StorefrontResponse:
        company_details = StorefrontCompanyDetails(
            established=str(org.established_year) if org.established_year else None,
            teamSize=org.team_size,
            exportMarkets=org.export_markets,
        )
        live = StorefrontService._is_live(org)
        return StorefrontResponse(
            live=live,
            liveLabel=StorefrontService.LIVE_LABEL,
            publicUrl=StorefrontService._public_url(org),
            slug=org.slug,
            published=org.storefront_published,
            name=org.name,
            verified=org.verification_status == VerificationStatus.APPROVED,
            tagline=org.tagline,
            category=org.category,
            location=StorefrontService._format_location(org),
            website=org.website,
            about=org.short_description or org.brand_story,
            bannerUrl=org.banner_url,
            bannerStyle=org.banner_style or "miu-brand",
            logoUrl=org.logo_url,
            companyDetails=company_details,
            stats=await StorefrontService._stats(db, org.id),
            featuredProducts=await StorefrontService._featured_products(db, org.id),
            certifications=await StorefrontService._certifications(db, org.id),
            gallery=await StorefrontService._gallery(db, org.id),
        )

    @staticmethod
    async def update_storefront(
        db: AsyncSession,
        org: SupplierOrganization,
        account: SupplierAccount,
        data: StorefrontUpdate,
    ) -> StorefrontResponse:
        updates = data.model_dump(exclude_unset=True)
        if "about" in updates:
            org.short_description = updates["about"]
        if "tagline" in updates:
            org.tagline = updates["tagline"]
        if "website" in updates:
            org.website = updates["website"]
        if "category" in updates:
            org.category = updates["category"]
        if "region" in updates:
            org.region = updates["region"]
        if "district" in updates:
            org.district = updates["district"]
        if "bannerUrl" in updates:
            org.banner_url = updates["bannerUrl"]
            if updates["bannerUrl"]:
                org.banner_style = None
        if "bannerStyle" in updates:
            org.banner_style = updates["bannerStyle"]
            if updates["bannerStyle"]:
                org.banner_url = None
        if "logoUrl" in updates:
            org.logo_url = updates["logoUrl"]
        if "establishedYear" in updates:
            org.established_year = updates["establishedYear"]
        if "teamSize" in updates:
            org.team_size = updates["teamSize"]
        if "exportMarkets" in updates:
            org.export_markets = updates["exportMarkets"]
        if "published" in updates and updates["published"] is not None:
            if updates["published"] and org.verification_status != VerificationStatus.APPROVED:
                raise AppError(403, "Supplier must be approved before publishing storefront", "not_approved")
            org.storefront_published = updates["published"]

        apply_update_audit(org, account.id)
        await db.flush()
        return await StorefrontService.get_storefront(db, org)

    @staticmethod
    async def set_published(
        db: AsyncSession,
        org: SupplierOrganization,
        account: SupplierAccount,
        published: bool,
    ) -> StorefrontResponse:
        org.storefront_published = published
        apply_update_audit(org, account.id)
        await db.flush()
        return await StorefrontService.get_storefront(db, org)

    @staticmethod
    async def _get_org_cert(
        db: AsyncSession,
        org_id: UUID,
        cert_id: UUID,
    ) -> SupplierCertification:
        cert = await db.get(SupplierCertification, cert_id)
        if not cert or cert.deleted_at or cert.org_id != org_id:
            raise AppError(404, "Certification not found", "not_found")
        return cert

    @staticmethod
    async def create_certification(
        db: AsyncSession,
        org: SupplierOrganization,
        account: SupplierAccount,
        data: CertificationCreate,
    ) -> StorefrontCertificationItem:
        cert = SupplierCertification(
            org_id=org.id,
            name=data.name.strip(),
            status=CertificationStatus(data.status),
            expiry_date=data.expiryDate,
            sort_order=data.sortOrder,
        )
        apply_create_audit(cert, account.id)
        db.add(cert)
        await db.flush()
        await db.refresh(cert)
        return StorefrontCertificationItem(
            id=cert.id,
            name=cert.name,
            status=cert.status.value,
            tone=StorefrontService._cert_tone(cert.status),
            expiryDate=cert.expiry_date,
            sortOrder=cert.sort_order,
        )

    @staticmethod
    async def update_certification(
        db: AsyncSession,
        org: SupplierOrganization,
        account: SupplierAccount,
        cert_id: UUID,
        data: CertificationUpdate,
    ) -> StorefrontCertificationItem:
        cert = await StorefrontService._get_org_cert(db, org.id, cert_id)
        updates = data.model_dump(exclude_unset=True)
        if "name" in updates and updates["name"] is not None:
            cert.name = updates["name"].strip()
        if "status" in updates and updates["status"] is not None:
            cert.status = CertificationStatus(updates["status"])
        if "expiryDate" in updates:
            cert.expiry_date = updates["expiryDate"]
        if "sortOrder" in updates and updates["sortOrder"] is not None:
            cert.sort_order = updates["sortOrder"]
        apply_update_audit(cert, account.id)
        await db.flush()
        await db.refresh(cert)
        return StorefrontCertificationItem(
            id=cert.id,
            name=cert.name,
            status=cert.status.value,
            tone=StorefrontService._cert_tone(cert.status),
            expiryDate=cert.expiry_date,
            sortOrder=cert.sort_order,
        )

    @staticmethod
    async def delete_certification(
        db: AsyncSession,
        org: SupplierOrganization,
        account: SupplierAccount,
        cert_id: UUID,
    ) -> None:
        cert = await StorefrontService._get_org_cert(db, org.id, cert_id)
        soft_delete(cert, account.id)

    @staticmethod
    async def _get_org_photo(
        db: AsyncSession,
        org_id: UUID,
        photo_id: UUID,
    ) -> SupplierGalleryPhoto:
        photo = await db.get(SupplierGalleryPhoto, photo_id)
        if not photo or photo.deleted_at or photo.org_id != org_id:
            raise AppError(404, "Gallery photo not found", "not_found")
        return photo

    @staticmethod
    async def create_gallery_photo(
        db: AsyncSession,
        org: SupplierOrganization,
        account: SupplierAccount,
        data: GalleryPhotoCreate,
    ) -> StorefrontGalleryItem:
        photo = SupplierGalleryPhoto(
            org_id=org.id,
            image_url=data.imageUrl.strip(),
            caption=data.caption.strip() if data.caption else None,
            sort_order=data.sortOrder,
        )
        apply_create_audit(photo, account.id)
        db.add(photo)
        await db.flush()
        await db.refresh(photo)
        return StorefrontGalleryItem(
            id=photo.id,
            imageUrl=photo.image_url,
            caption=photo.caption,
            sortOrder=photo.sort_order,
        )

    @staticmethod
    async def update_gallery_photo(
        db: AsyncSession,
        org: SupplierOrganization,
        account: SupplierAccount,
        photo_id: UUID,
        data: GalleryPhotoUpdate,
    ) -> StorefrontGalleryItem:
        photo = await StorefrontService._get_org_photo(db, org.id, photo_id)
        updates = data.model_dump(exclude_unset=True)
        if "imageUrl" in updates and updates["imageUrl"] is not None:
            photo.image_url = updates["imageUrl"].strip()
        if "caption" in updates:
            photo.caption = updates["caption"].strip() if updates["caption"] else None
        if "sortOrder" in updates and updates["sortOrder"] is not None:
            photo.sort_order = updates["sortOrder"]
        apply_update_audit(photo, account.id)
        await db.flush()
        await db.refresh(photo)
        return StorefrontGalleryItem(
            id=photo.id,
            imageUrl=photo.image_url,
            caption=photo.caption,
            sortOrder=photo.sort_order,
        )

    @staticmethod
    async def delete_gallery_photo(
        db: AsyncSession,
        org: SupplierOrganization,
        account: SupplierAccount,
        photo_id: UUID,
    ) -> None:
        photo = await StorefrontService._get_org_photo(db, org.id, photo_id)
        soft_delete(photo, account.id)

    @staticmethod
    async def upload_banner(
        db: AsyncSession,
        org: SupplierOrganization,
        account: SupplierAccount,
        file: UploadFile,
    ) -> StorefrontResponse:
        content = await file.read()
        if not content:
            raise AppError(400, "Empty file", "empty_file")
        settings = get_settings()
        mime = file.content_type or "image/jpeg"
        suffix = Path(file.filename or "banner.jpg").suffix.lower() or ".jpg"
        if mime not in settings.mime_allowlist:
            raise AppError(400, f"File type not allowed: {mime}", "invalid_mime")
        record = await store_upload_bytes(
            db,
            content=content,
            mime_type=mime,
            suffix=suffix,
            uploaded_by=account.id,
            subdirectory=f"storefront/{org.id}/banner",
        )
        await db.refresh(org)
        org.banner_url = public_file_url(record.storage_key)
        org.banner_style = None
        apply_update_audit(org, account.id)
        await db.flush()
        return await StorefrontService.get_storefront(db, org)

    @staticmethod
    async def upload_logo(
        db: AsyncSession,
        org: SupplierOrganization,
        account: SupplierAccount,
        file: UploadFile,
    ) -> StorefrontResponse:
        content = await file.read()
        if not content:
            raise AppError(400, "Empty file", "empty_file")
        settings = get_settings()
        mime = file.content_type or "image/jpeg"
        suffix = Path(file.filename or "logo.jpg").suffix.lower() or ".jpg"
        if mime not in settings.mime_allowlist:
            raise AppError(400, f"File type not allowed: {mime}", "invalid_mime")
        record = await store_upload_bytes(
            db,
            content=content,
            mime_type=mime,
            suffix=suffix,
            uploaded_by=account.id,
            subdirectory=f"storefront/{org.id}/logo",
        )
        await db.refresh(org)
        org.logo_url = public_file_url(record.storage_key)
        apply_update_audit(org, account.id)
        await db.flush()
        return await StorefrontService.get_storefront(db, org)

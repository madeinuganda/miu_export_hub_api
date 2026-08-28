"""Admin moderation gate for supplier product listings.

Suppliers can only move a listing between DRAFT and PENDING_REVIEW; PUBLISHED
and REJECTED are set by MIU admins. Editing review-relevant content on a live
listing sends it back to the queue so buyers never see unreviewed changes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.models.export_hub.accounts import SupplierAccount
from app.models.export_hub.catalog import Product, ProductCertification
from app.models.export_hub.organizations import SupplierOrganizationMember
from app.models.shared.enums import ProductStatus
from app.services.shared.email_service import EmailService
from app.utils.audit import apply_update_audit

logger = logging.getLogger(__name__)

# Statuses a supplier is allowed to ask for directly.
SUPPLIER_SETTABLE = {
    "draft": ProductStatus.DRAFT,
    "archived": ProductStatus.ARCHIVED,
}

PRODUCT_STATUS_LABELS = {
    ProductStatus.DRAFT.value: "Draft",
    ProductStatus.PENDING_REVIEW.value: "Pending review",
    ProductStatus.PUBLISHED.value: "Published",
    ProductStatus.REJECTED.value: "Changes requested",
    ProductStatus.ARCHIVED.value: "Archived",
}


def product_status_label(status: str) -> str:
    return PRODUCT_STATUS_LABELS.get(status, status.replace("_", " ").title())


def resolve_supplier_status(raw: str | None, current: ProductStatus | None) -> ProductStatus:
    """Map a supplier-supplied status onto what they are actually allowed to set.

    Anything that is not an explicit draft/archive request means "make this
    live", which becomes PENDING_REVIEW rather than PUBLISHED.
    """
    key = str(raw or "draft").strip().lower()
    if key in SUPPLIER_SETTABLE:
        return SUPPLIER_SETTABLE[key]
    if current == ProductStatus.PUBLISHED:
        return ProductStatus.PUBLISHED
    return ProductStatus.PENDING_REVIEW


def review_fingerprint(product: Product, certifications: list[str]) -> tuple:
    """Fields a reviewer checks — a change to any of these re-opens review."""
    return (
        (product.name or "").strip(),
        (product.description or "").strip(),
        (product.origin_story or "").strip(),
        str(product.category_id or ""),
        (product.subcategory or "").strip(),
        str(product.price_amount if product.price_amount is not None else ""),
        str(product.moq_value if product.moq_value is not None else ""),
        (product.moq_unit or "").strip(),
        product.lead_time_days,
        tuple(sorted(c.strip() for c in certifications if c and c.strip())),
    )


async def product_certifications(db: AsyncSession, product_id: UUID) -> list[str]:
    rows = (
        await db.execute(
            select(ProductCertification.certification_name).where(
                ProductCertification.product_id == product_id,
                ProductCertification.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    return list(rows)


def mark_submitted(product: Product, actor_id: UUID) -> None:
    product.status = ProductStatus.PENDING_REVIEW
    product.submitted_at = datetime.now(timezone.utc)
    product.reviewed_at = None
    product.reviewed_by = None
    product.review_note = None
    product.featured = False
    apply_update_audit(product, actor_id)


class ProductReviewService:
    @staticmethod
    async def _supplier_recipient(
        db: AsyncSession, supplier_org_id: UUID
    ) -> SupplierAccount | None:
        member = (
            await db.execute(
                select(SupplierOrganizationMember)
                .where(
                    SupplierOrganizationMember.org_id == supplier_org_id,
                    SupplierOrganizationMember.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if not member:
            return None
        return await db.get(SupplierAccount, member.supplier_account_id)

    @staticmethod
    def _product_url(product: Product) -> str:
        base = get_settings().frontend_base_url.rstrip("/")
        return f"{base}/dashboard/supplier/products/{product.id}"

    @staticmethod
    async def notify_submitted(db: AsyncSession, product: Product) -> None:
        account = await ProductReviewService._supplier_recipient(
            db, product.supplier_org_id
        )
        if not account or not account.email:
            return
        await EmailService.send_product_submitted_email(
            to_email=account.email,
            first_name=account.first_name or "there",
            product_name=product.name,
            product_url=ProductReviewService._product_url(product),
        )

    @staticmethod
    async def submit_for_review(
        db: AsyncSession, org_id: UUID, actor_id: UUID, product_id: UUID
    ) -> dict:
        product = await db.get(Product, product_id)
        if not product or product.deleted_at or product.supplier_org_id != org_id:
            raise AppError(404, "Product not found", "not_found")
        if product.status == ProductStatus.PENDING_REVIEW:
            raise AppError(400, "This listing is already awaiting review", "invalid_status")
        if product.status == ProductStatus.PUBLISHED:
            raise AppError(400, "This listing is already published", "invalid_status")

        if not (product.description or "").strip():
            raise AppError(
                400,
                "Add a product description before submitting for review",
                "validation_error",
            )
        if product.price_amount is None or Decimal(product.price_amount) <= 0:
            raise AppError(
                400, "Set a price before submitting for review", "validation_error"
            )

        mark_submitted(product, actor_id)
        await db.flush()
        await ProductReviewService.notify_submitted(db, product)
        return {
            "id": str(product.id),
            "status": product.status.value,
            "statusLabel": product_status_label(product.status.value),
        }

    @staticmethod
    async def review(
        db: AsyncSession,
        admin_id: UUID,
        product_id: UUID,
        *,
        approved: bool,
        note: str | None,
    ) -> dict:
        product = await db.get(Product, product_id)
        if not product or product.deleted_at:
            raise AppError(404, "Product not found", "not_found")
        if product.status not in (ProductStatus.PENDING_REVIEW, ProductStatus.REJECTED):
            raise AppError(
                400,
                "Only a listing awaiting review can be approved or rejected",
                "invalid_status",
            )
        cleaned_note = (note or "").strip()
        if not approved and not cleaned_note:
            raise AppError(
                422, "Tell the supplier what needs to change", "validation_error"
            )

        product.status = ProductStatus.PUBLISHED if approved else ProductStatus.REJECTED
        product.reviewed_at = datetime.now(timezone.utc)
        product.reviewed_by = admin_id
        product.review_note = cleaned_note or None
        apply_update_audit(product, admin_id)
        await db.flush()

        account = await ProductReviewService._supplier_recipient(
            db, product.supplier_org_id
        )
        if account and account.email:
            url = ProductReviewService._product_url(product)
            if approved:
                await EmailService.send_product_approved_email(
                    to_email=account.email,
                    first_name=account.first_name or "there",
                    product_name=product.name,
                    product_url=url,
                )
            else:
                await EmailService.send_product_rejected_email(
                    to_email=account.email,
                    first_name=account.first_name or "there",
                    product_name=product.name,
                    reason=cleaned_note,
                    product_url=url,
                )

        return {
            "id": str(product.id),
            "status": product.status.value,
            "statusLabel": product_status_label(product.status.value),
            "reviewNote": product.review_note,
        }

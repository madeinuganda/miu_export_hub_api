from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.models.export_hub.accounts import BuyerAccount
from app.models.export_hub.catalog import Product
from app.models.export_hub.orders import Order
from app.models.export_hub.reviews import ExportHubProductReview
from app.models.shared.enums import OrderStatus, ProductStatus
from app.schemas.export_hub.review import ReviewCreateRequest
from app.utils.audit import apply_create_audit


class ExportHubReviewService:
    @staticmethod
    async def list_product_reviews(
        db: AsyncSession,
        product_id: UUID,
        *,
        limit: int = 10,
        offset: int = 1,
    ) -> dict:
        base = select(ExportHubProductReview).where(
            ExportHubProductReview.product_id == product_id,
            ExportHubProductReview.deleted_at.is_(None),
        )
        total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        rows = (
            await db.execute(
                base.order_by(ExportHubProductReview.created_at.desc())
                .offset((offset - 1) * limit)
                .limit(limit)
            )
        ).scalars().all()
        return {
            "total_size": total,
            "reviews": [
                {
                    "id": str(r.id),
                    "rating": r.rating,
                    "title": r.title,
                    "comment": r.comment,
                    "reviewer_name": r.reviewer_name,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
        }

    @staticmethod
    async def _buyer_purchased_product(
        db: AsyncSession,
        buyer_org_id: UUID,
        product_id: UUID,
        order_id: UUID | None,
    ) -> bool:
        query = select(Order.id).where(
            Order.buyer_org_id == buyer_org_id,
            Order.product_id == product_id,
            Order.status.in_([OrderStatus.DELIVERED, OrderStatus.FULFILLED]),
            Order.deleted_at.is_(None),
        )
        if order_id:
            query = query.where(Order.id == order_id)
        return (await db.execute(query.limit(1))).scalar_one_or_none() is not None

    @staticmethod
    async def submit_review(
        db: AsyncSession,
        buyer_org_id: UUID,
        account: BuyerAccount,
        data: ReviewCreateRequest,
    ) -> dict:
        product = await db.get(Product, data.product_id)
        if not product or product.deleted_at or product.status != ProductStatus.PUBLISHED:
            raise AppError(404, "Product not found", "not_found")

        existing = (
            await db.execute(
                select(ExportHubProductReview).where(
                    ExportHubProductReview.product_id == data.product_id,
                    ExportHubProductReview.buyer_org_id == buyer_org_id,
                    ExportHubProductReview.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise AppError(409, "You already reviewed this product", "review_exists")

        if not await ExportHubReviewService._buyer_purchased_product(
            db, buyer_org_id, data.product_id, data.order_id
        ):
            raise AppError(403, "You can only review delivered products you purchased", "not_eligible")

        reviewer_name = f"{account.first_name} {account.last_name}".strip() or account.email
        row = ExportHubProductReview(
            product_id=data.product_id,
            buyer_org_id=buyer_org_id,
            buyer_account_id=account.id,
            order_id=data.order_id,
            rating=data.rating,
            title=data.title,
            comment=data.comment,
            reviewer_name=reviewer_name,
        )
        apply_create_audit(row, account.id)
        db.add(row)
        await db.flush()

        stats = (
            await db.execute(
                select(
                    func.count(ExportHubProductReview.id),
                    func.coalesce(func.avg(ExportHubProductReview.rating), 0),
                ).where(
                    ExportHubProductReview.product_id == data.product_id,
                    ExportHubProductReview.deleted_at.is_(None),
                )
            )
        ).one()
        product.review_count = int(stats[0])
        product.rating = Decimal(str(round(float(stats[1]), 2)))
        await db.flush()
        return {"id": str(row.id), "message": "review_submitted"}

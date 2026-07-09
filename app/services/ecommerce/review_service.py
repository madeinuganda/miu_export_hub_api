from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.models.ecommerce.accounts import CustomerAccount
from app.models.ecommerce.catalog import EcommerceProduct
from app.models.ecommerce.orders import EcommerceOrder, EcommerceOrderItem
from app.models.ecommerce.reviews import EcommerceProductReview
from app.models.shared.enums import EcommerceOrderStatus
from app.schemas.ecommerce.review import ReviewCreateRequest
from app.utils.audit import apply_create_audit


class EcommerceReviewService:
  @staticmethod
  async def list_product_reviews(
    db: AsyncSession, product_id: UUID, *, limit: int = 10, offset: int = 1
  ) -> dict:
    base = select(EcommerceProductReview).where(
      EcommerceProductReview.product_id == product_id,
      EcommerceProductReview.deleted_at.is_(None),
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
      await db.execute(
        base.order_by(EcommerceProductReview.created_at.desc())
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
          "customer_name": r.customer_name,
          "created_at": r.created_at.isoformat(),
        }
        for r in rows
      ],
    }

  @staticmethod
  async def _customer_purchased_product(
    db: AsyncSession, customer_id: UUID, product_id: UUID, order_id: UUID | None
  ) -> bool:
    query = (
      select(EcommerceOrderItem.id)
      .join(EcommerceOrder, EcommerceOrder.id == EcommerceOrderItem.order_id)
      .where(
        EcommerceOrder.customer_id == customer_id,
        EcommerceOrderItem.product_id == product_id,
        EcommerceOrder.order_status == EcommerceOrderStatus.DELIVERED,
        EcommerceOrder.deleted_at.is_(None),
      )
    )
    if order_id:
      query = query.where(EcommerceOrder.id == order_id)
    return (await db.execute(query.limit(1))).scalar_one_or_none() is not None

  @staticmethod
  async def submit_review(
    db: AsyncSession, customer: CustomerAccount, data: ReviewCreateRequest
  ) -> dict:
    product = await db.get(EcommerceProduct, data.product_id)
    if not product or product.deleted_at:
      raise AppError(404, "Product not found", "not_found")

    existing = (
      await db.execute(
        select(EcommerceProductReview).where(
          EcommerceProductReview.product_id == data.product_id,
          EcommerceProductReview.customer_id == customer.id,
          EcommerceProductReview.deleted_at.is_(None),
        )
      )
    ).scalar_one_or_none()
    if existing:
      raise AppError(409, "You already reviewed this product", "review_exists")

    if not await EcommerceReviewService._customer_purchased_product(
      db, customer.id, data.product_id, data.order_id
    ):
      raise AppError(403, "You can only review delivered products you purchased", "not_eligible")

    row = EcommerceProductReview(
      product_id=data.product_id,
      customer_id=customer.id,
      order_id=data.order_id,
      rating=data.rating,
      title=data.title,
      comment=data.comment,
      customer_name=f"{customer.first_name} {customer.last_name}".strip(),
    )
    apply_create_audit(row, customer.id)
    db.add(row)
    await db.flush()

    stats = (
      await db.execute(
        select(
          func.count(EcommerceProductReview.id),
          func.coalesce(func.avg(EcommerceProductReview.rating), 0),
        ).where(
          EcommerceProductReview.product_id == data.product_id,
          EcommerceProductReview.deleted_at.is_(None),
        )
      )
    ).one()
    product.reviews_count = stats[0]
    product.average_review = Decimal(str(round(float(stats[1]), 2)))
    await db.flush()
    return {"id": str(row.id), "message": "review_submitted"}

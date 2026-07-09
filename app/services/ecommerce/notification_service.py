from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ecommerce.notifications import EcommerceCustomerNotification
from app.services.shared.notifications.email_delivery import EmailDeliveryService
from app.utils.audit import apply_create_audit, apply_update_audit


class EcommerceNotificationService:
  @staticmethod
  async def notify_customer(
    db: AsyncSession,
    *,
    customer_id: UUID,
    title: str,
    body: str,
    notification_type: str,
    reference_id: UUID | None = None,
    email: str | None = None,
    send_email: bool = True,
  ) -> EcommerceCustomerNotification:
    row = EcommerceCustomerNotification(
      customer_id=customer_id,
      title=title,
      body=body,
      notification_type=notification_type,
      reference_id=reference_id,
    )
    apply_create_audit(row, customer_id)
    db.add(row)
    await db.flush()

    if send_email and email:
      try:
        await EmailDeliveryService.send(to=email, subject=title, body=body)
      except Exception:
        pass
    return row

  @staticmethod
  async def list_notifications(
    db: AsyncSession, customer_id: UUID, *, limit: int = 20, offset: int = 1
  ) -> dict:
    base = select(EcommerceCustomerNotification).where(
      EcommerceCustomerNotification.customer_id == customer_id,
      EcommerceCustomerNotification.deleted_at.is_(None),
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    unread = (
      await db.execute(
        select(func.count()).where(
          EcommerceCustomerNotification.customer_id == customer_id,
          EcommerceCustomerNotification.is_read.is_(False),
          EcommerceCustomerNotification.deleted_at.is_(None),
        )
      )
    ).scalar_one()
    rows = (
      await db.execute(
        base.order_by(EcommerceCustomerNotification.created_at.desc())
        .offset((offset - 1) * limit)
        .limit(limit)
      )
    ).scalars().all()
    return {
      "total_size": total,
      "unread_count": unread,
      "notifications": [
        {
          "id": str(n.id),
          "title": n.title,
          "body": n.body,
          "notification_type": n.notification_type,
          "reference_id": str(n.reference_id) if n.reference_id else None,
          "is_read": n.is_read,
          "created_at": n.created_at.isoformat(),
        }
        for n in rows
      ],
    }

  @staticmethod
  async def mark_read(db: AsyncSession, customer_id: UUID, notification_id: UUID) -> dict:
    row = (
      await db.execute(
        select(EcommerceCustomerNotification).where(
          EcommerceCustomerNotification.id == notification_id,
          EcommerceCustomerNotification.customer_id == customer_id,
          EcommerceCustomerNotification.deleted_at.is_(None),
        )
      )
    ).scalar_one_or_none()
    if not row:
      return {"message": "not_found"}
    row.is_read = True
    apply_update_audit(row, customer_id)
    await db.flush()
    return {"message": "marked_read"}

  @staticmethod
  async def mark_all_read(db: AsyncSession, customer_id: UUID) -> dict:
    await db.execute(
      update(EcommerceCustomerNotification)
      .where(
        EcommerceCustomerNotification.customer_id == customer_id,
        EcommerceCustomerNotification.is_read.is_(False),
        EcommerceCustomerNotification.deleted_at.is_(None),
      )
      .values(is_read=True)
    )
    return {"message": "all_marked_read"}

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.models.export_hub.accounts import BuyerAccount
from app.models.export_hub.catalog import Product
from app.models.export_hub.orders import Order, OrderActivity
from app.models.export_hub.organizations import BuyerOrganization
from app.models.export_hub.payments import PaymentEscrow, PaymentLink, PaymentMilestone
from app.models.shared.enums import EscrowStatus, OrderStatus, PaymentMilestoneStatus
from app.services.ecommerce.pesapal_service import PesapalService
from app.services.export_hub.order_service import OrderService, PIPELINE_BY_STAGE
from app.utils.audit import apply_update_audit
from app.utils.formatting import format_ugx


class PaymentService:
    @staticmethod
    def _delivered_pipeline_index() -> int:
        return PIPELINE_BY_STAGE["delivered"][0]

    @staticmethod
    async def _milestones_for_escrow(db: AsyncSession, escrow_id: UUID) -> dict[str, PaymentMilestone]:
        rows = (
            await db.execute(
                select(PaymentMilestone).where(
                    PaymentMilestone.escrow_id == escrow_id,
                    PaymentMilestone.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        return {row.milestone_type: row for row in rows}

    @staticmethod
    def _upfront_status(escrow: PaymentEscrow, milestone: PaymentMilestone | None) -> str:
        if escrow.status in (EscrowStatus.UPFRONT_RECEIVED, EscrowStatus.BALANCE_RELEASED):
            return "received"
        if milestone and milestone.status == PaymentMilestoneStatus.RECEIVED:
            return "received"
        return "pending_delivery"

    @staticmethod
    def _balance_status(escrow: PaymentEscrow, milestone: PaymentMilestone | None) -> str:
        if escrow.status == EscrowStatus.BALANCE_RELEASED:
            return "released"
        if milestone and milestone.status == PaymentMilestoneStatus.RELEASED:
            return "released"
        return "pending_delivery"

    @staticmethod
    async def supplier_payments_summary(db: AsyncSession, supplier_org_id: UUID) -> dict:
        rows = (
            await db.execute(
                select(PaymentEscrow, Order)
                .join(Order, Order.id == PaymentEscrow.order_id)
                .where(
                    Order.supplier_org_id == supplier_org_id,
                    PaymentEscrow.deleted_at.is_(None),
                    Order.deleted_at.is_(None),
                )
                .order_by(Order.created_at.desc())
            )
        ).all()

        total_received = Decimal("0")
        pending_on_delivery = Decimal("0")
        in_escrow = Decimal("0")
        pending_delivery_count = 0
        delivered_index = PaymentService._delivered_pipeline_index()

        for escrow, order in rows:
            if escrow.status == EscrowStatus.PENDING:
                continue

            milestones = await PaymentService._milestones_for_escrow(db, escrow.id)
            upfront_milestone = milestones.get("upfront")
            balance_milestone = milestones.get("balance")

            if PaymentService._upfront_status(escrow, upfront_milestone) == "received":
                total_received += escrow.upfront_amount
            if PaymentService._balance_status(escrow, balance_milestone) == "released":
                total_received += escrow.balance_amount

            pipeline_index = OrderService.order_pipeline_index(order)
            balance_pending = PaymentService._balance_status(escrow, balance_milestone) == "pending_delivery"

            if balance_pending and pipeline_index >= delivered_index:
                pending_on_delivery += escrow.balance_amount
                pending_delivery_count += 1
            elif escrow.status == EscrowStatus.UPFRONT_RECEIVED and pipeline_index < delivered_index:
                in_escrow += escrow.upfront_amount

        return {
            "totalReceived": format_ugx(total_received),
            "totalReceivedHint": "Across all orders",
            "pendingOnDelivery": format_ugx(pending_on_delivery),
            "pendingOnDeliveryHint": (
                f"{pending_delivery_count} order{'s' if pending_delivery_count != 1 else ''} awaiting delivery confirmation"
                if pending_delivery_count
                else "No orders awaiting delivery confirmation"
            ),
            "inEscrow": format_ugx(in_escrow),
            "inEscrowHint": "Secured — awaiting production completion",
        }

    @staticmethod
    async def supplier_payments_list(db: AsyncSession, supplier_org_id: UUID) -> dict:
        rows = (
            await db.execute(
                select(PaymentEscrow, Order)
                .join(Order, Order.id == PaymentEscrow.order_id)
                .where(
                    Order.supplier_org_id == supplier_org_id,
                    PaymentEscrow.deleted_at.is_(None),
                    Order.deleted_at.is_(None),
                )
                .order_by(Order.created_at.desc())
            )
        ).all()

        items: list[dict] = []
        for escrow, order in rows:
            if escrow.status == EscrowStatus.PENDING:
                continue

            product = await db.get(Product, order.product_id)
            buyer = await db.get(BuyerOrganization, order.buyer_org_id)
            milestones = await PaymentService._milestones_for_escrow(db, escrow.id)
            upfront_milestone = milestones.get("upfront")
            balance_milestone = milestones.get("balance")

            items.append(
                {
                    "orderId": order.public_id,
                    "date": order.created_at.date().isoformat(),
                    "product": product.name if product else "",
                    "buyer": buyer.name if buyer else "Verified Buyer",
                    "totalValue": format_ugx(escrow.total_amount),
                    "upfront": {
                        "amount": format_ugx(escrow.upfront_amount),
                        "status": PaymentService._upfront_status(escrow, upfront_milestone),
                    },
                    "balance": {
                        "amount": format_ugx(escrow.balance_amount),
                        "status": PaymentService._balance_status(escrow, balance_milestone),
                    },
                }
            )

        return {
            "items": items,
            "tradeAssurance": {"upfrontPercent": 70, "balancePercent": 30},
        }

    @staticmethod
    async def _owned_order_with_escrow(
        db: AsyncSession,
        buyer_org_id: UUID,
        public_id: str,
    ) -> tuple[Order, PaymentEscrow, PaymentLink]:
        order = (
            await db.execute(
                select(Order).where(
                    Order.public_id == public_id,
                    Order.buyer_org_id == buyer_org_id,
                    Order.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not order:
            raise AppError(404, "Order not found", "not_found")

        escrow = (
            await db.execute(
                select(PaymentEscrow).where(
                    PaymentEscrow.order_id == order.id,
                    PaymentEscrow.deleted_at.is_(None),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if not escrow:
            raise AppError(404, "Escrow not found", "not_found")

        link = (
            await db.execute(
                select(PaymentLink)
                .where(
                    PaymentLink.escrow_id == escrow.id,
                    PaymentLink.deleted_at.is_(None),
                )
                .order_by(PaymentLink.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not link:
            raise AppError(404, "Payment link not found", "not_found")

        return order, escrow, link

    @staticmethod
    async def initiate_order_payment(
        db: AsyncSession,
        buyer_org_id: UUID,
        account: BuyerAccount,
        public_id: str,
        payment_link_token: str | None = None,
    ) -> dict:
        order, escrow, link = await PaymentService._owned_order_with_escrow(db, buyer_org_id, public_id)

        if payment_link_token and link.token != payment_link_token:
            raise AppError(400, "Invalid payment link", "invalid_payment_link")

        if link.expires_at < datetime.now(timezone.utc):
            raise AppError(400, "Payment link expired", "payment_link_expired")

        settings = get_settings()
        if escrow.status != EscrowStatus.PENDING:
            return {
                "redirect_link": (
                    f"{settings.frontend_base_url.rstrip('/')}/dashboard/buyer/orders"
                    f"?order={order.public_id}"
                ),
                "payment_id": str(link.id),
                "order_id": order.public_id,
            }

        redirect_link = (
            f"{settings.api_base_url.rstrip('/')}/api/v1/export-hub/payments/pesapal/pay"
            f"?token={link.token}"
        )

        if not settings.pesapal_enabled:
            await PaymentService._fulfill_upfront_payment(
                db, order, escrow, link, account.id, transaction_ref="demo"
            )
            return {
                "redirect_link": (
                    f"{settings.frontend_base_url.rstrip('/')}/dashboard/buyer/orders"
                    f"?order={order.public_id}&payment=success"
                ),
                "payment_id": str(link.id),
                "order_id": order.public_id,
            }

        return {
            "redirect_link": redirect_link,
            "payment_id": str(link.id),
            "order_id": order.public_id,
        }

    @staticmethod
    async def pesapal_pay_redirect(db: AsyncSession, token: str, payer: dict) -> str:
        link = (
            await db.execute(
                select(PaymentLink).where(
                    PaymentLink.token == token,
                    PaymentLink.deleted_at.is_(None),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if not link:
            raise AppError(404, "Payment link not found", "not_found")

        escrow = await db.get(PaymentEscrow, link.escrow_id)
        if not escrow or escrow.deleted_at is not None:
            raise AppError(404, "Escrow not found", "not_found")

        order = await db.get(Order, escrow.order_id)
        settings = get_settings()

        if escrow.status != EscrowStatus.PENDING:
            return (
                f"{settings.frontend_base_url.rstrip('/')}/dashboard/buyer/orders"
                f"?order={order.public_id if order else ''}&payment=success"
            )

        if not settings.pesapal_enabled:
            await PaymentService._fulfill_upfront_payment(
                db,
                order,
                escrow,
                link,
                link.updated_by or link.created_by,
                transaction_ref="demo",
            )
            return (
                f"{settings.frontend_base_url.rstrip('/')}/dashboard/buyer/orders"
                f"?order={order.public_id if order else ''}&payment=success"
            )

        callback_url = (
            f"{settings.api_base_url.rstrip('/')}/api/v1/export-hub/payments/pesapal/callback"
            f"?token={token}"
        )
        product = await db.get(Product, order.product_id) if order else None
        description = f"MIU Trade Assurance — {order.public_id if order else token}"
        if product and order:
            description = f"MIU order {order.public_id} — {product.name}"

        return await PesapalService.submit_order_request(
            payment_id=token,
            amount=escrow.upfront_amount,
            currency=escrow.currency,
            description=description,
            callback_url=callback_url,
            payer=payer,
        )

    @staticmethod
    async def _fulfill_upfront_payment(
        db: AsyncSession,
        order: Order,
        escrow: PaymentEscrow,
        link: PaymentLink,
        actor_id: UUID,
        *,
        transaction_ref: str | None = None,
    ) -> None:
        if escrow.status != EscrowStatus.PENDING:
            return

        escrow.status = EscrowStatus.UPFRONT_RECEIVED
        apply_update_audit(escrow, actor_id)

        order.status = OrderStatus.PAYMENT_SECURED
        apply_update_audit(order, actor_id)
        await OrderService.sync_pipeline_milestones(
            db,
            order,
            PIPELINE_BY_STAGE["payment_secured"][0],
            actor_id,
        )

        milestones = await PaymentService._milestones_for_escrow(db, escrow.id)
        upfront = milestones.get("upfront")
        if upfront:
            upfront.status = PaymentMilestoneStatus.RECEIVED
            apply_update_audit(upfront, actor_id)
        else:
            db.add(
                PaymentMilestone(
                    escrow_id=escrow.id,
                    milestone_type="upfront",
                    amount=escrow.upfront_amount,
                    status=PaymentMilestoneStatus.RECEIVED,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

        if "balance" not in milestones:
            db.add(
                PaymentMilestone(
                    escrow_id=escrow.id,
                    milestone_type="balance",
                    amount=escrow.balance_amount,
                    status=PaymentMilestoneStatus.PENDING,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

        link.paid_at = datetime.now(timezone.utc)
        apply_update_audit(link, actor_id)

        db.add(
            OrderActivity(
                order_id=order.id,
                occurred_at=datetime.now(timezone.utc),
                description="Trade assurance payment secured.",
                created_by=actor_id,
                updated_by=actor_id,
            )
        )

        if transaction_ref:
            db.add(
                OrderActivity(
                    order_id=order.id,
                    occurred_at=datetime.now(timezone.utc),
                    description=f"Payment reference: {transaction_ref}",
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    @staticmethod
    async def process_pesapal_callback(
        db: AsyncSession,
        token: str,
        order_tracking_id: str | None,
    ) -> tuple[bool, str]:
        settings = get_settings()
        link = (
            await db.execute(
                select(PaymentLink).where(
                    PaymentLink.token == token,
                    PaymentLink.deleted_at.is_(None),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if not link:
            raise AppError(404, "Payment link not found", "not_found")

        escrow = await db.get(PaymentEscrow, link.escrow_id)
        if not escrow or escrow.deleted_at is not None:
            raise AppError(404, "Escrow not found", "not_found")

        order = await db.get(Order, escrow.order_id)
        order_public_id = order.public_id if order else ""

        if not order_tracking_id:
            return False, (
                f"{settings.frontend_base_url.rstrip('/')}/dashboard/buyer/orders"
                f"?order={order_public_id}&payment=failed"
            )

        if escrow.status != EscrowStatus.PENDING:
            return True, (
                f"{settings.frontend_base_url.rstrip('/')}/dashboard/buyer/orders"
                f"?order={order_public_id}&payment=success"
            )

        status_payload = await PesapalService.get_transaction_status(order_tracking_id)
        if PesapalService.is_payment_successful(
            status_payload, escrow.upfront_amount, escrow.currency
        ):
            await PaymentService._fulfill_upfront_payment(
                db,
                order,
                escrow,
                link,
                link.updated_by or link.created_by,
                transaction_ref=order_tracking_id,
            )
            return True, (
                f"{settings.frontend_base_url.rstrip('/')}/dashboard/buyer/orders"
                f"?order={order_public_id}&payment=success"
            )

        return False, (
            f"{settings.frontend_base_url.rstrip('/')}/dashboard/buyer/orders"
            f"?order={order_public_id}&payment=failed"
        )

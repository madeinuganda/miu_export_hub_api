from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.models.ecommerce.accounts import CustomerAccount
from app.models.ecommerce.orders import EcommercePaymentRequest
from app.models.ecommerce.wallet import EcommerceWalletTransaction
from app.models.shared.enums import (
    EcommercePaymentPurpose,
    EcommerceWalletTransactionType,
)
from app.services.ecommerce.pesapal_service import PesapalService


class EcommerceWalletService:
    @staticmethod
    async def get_balance(db: AsyncSession, customer_id: UUID) -> Decimal:
        account = (
            await db.execute(
                select(CustomerAccount).where(
                    CustomerAccount.id == customer_id,
                    CustomerAccount.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not account:
            raise AppError(404, "Customer not found", "customer_not_found")
        return account.wallet_balance

    @staticmethod
    async def list_transactions(
        db: AsyncSession,
        customer_id: UUID,
        limit: int = 10,
        offset: int = 1,
    ) -> dict:
        settings = get_settings()
        if not settings.ecommerce_wallet_enabled:
            raise AppError(403, "Wallet is disabled", "wallet_disabled")

        balance = await EcommerceWalletService.get_balance(db, customer_id)
        query = select(EcommerceWalletTransaction).where(
            EcommerceWalletTransaction.customer_id == customer_id,
            EcommerceWalletTransaction.deleted_at.is_(None),
        )
        total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        page = max(offset, 1)
        skip = (page - 1) * limit
        rows = (
            await db.execute(
                query.order_by(EcommerceWalletTransaction.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
        ).scalars().all()
        return {
            "total_wallet_balance": float(balance),
            "currency": "UGX",
            "total_size": total,
            "limit": limit,
            "offset": page,
            "transactions": [
                {
                    "id": str(row.id),
                    "transaction_ref": row.transaction_ref,
                    "credit": float(row.credit),
                    "debit": float(row.debit),
                    "balance_after": float(row.balance_after),
                    "transaction_type": row.transaction_type.value,
                    "reference": row.reference,
                    "payment_method": row.payment_method,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ],
        }

    @staticmethod
    async def _apply_transaction(
        db: AsyncSession,
        customer_id: UUID,
        *,
        credit: Decimal = Decimal("0"),
        debit: Decimal = Decimal("0"),
        transaction_type: EcommerceWalletTransactionType,
        reference: str,
        payment_method: str | None = None,
    ) -> EcommerceWalletTransaction:
        account = (
            await db.execute(
                select(CustomerAccount).where(
                    CustomerAccount.id == customer_id,
                    CustomerAccount.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not account:
            raise AppError(404, "Customer not found", "customer_not_found")

        new_balance = account.wallet_balance + credit - debit
        if new_balance < 0:
            raise AppError(400, "Insufficient wallet balance", "insufficient_balance")

        account.wallet_balance = new_balance
        row = EcommerceWalletTransaction(
            customer_id=customer_id,
            transaction_ref=str(uuid4()),
            credit=credit,
            debit=debit,
            balance_after=new_balance,
            transaction_type=transaction_type,
            reference=reference,
            payment_method=payment_method,
        )
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def credit_add_fund(
        db: AsyncSession,
        customer_id: UUID,
        amount: Decimal,
        payment_method: str | None = None,
    ) -> EcommerceWalletTransaction:
        return await EcommerceWalletService._apply_transaction(
            db,
            customer_id,
            credit=amount,
            transaction_type=EcommerceWalletTransactionType.ADD_FUND,
            reference="add_funds_to_wallet",
            payment_method=payment_method,
        )

    @staticmethod
    async def debit_order_payment(
        db: AsyncSession,
        customer_id: UUID,
        amount: Decimal,
    ) -> EcommerceWalletTransaction:
        return await EcommerceWalletService._apply_transaction(
            db,
            customer_id,
            debit=amount,
            transaction_type=EcommerceWalletTransactionType.ORDER_PLACE,
            reference="order payment",
            payment_method="wallet",
        )

    @staticmethod
    async def create_add_fund_request(
        db: AsyncSession,
        customer: CustomerAccount,
        amount: Decimal,
        payment_method: str = "pesapal",
    ) -> EcommercePaymentRequest:
        settings = get_settings()
        if not settings.ecommerce_wallet_enabled:
            raise AppError(403, "Wallet is disabled", "wallet_disabled")
        if amount < Decimal(str(settings.ecommerce_wallet_min_add_fund)):
            raise AppError(400, "Amount below minimum add-fund limit", "amount_too_low")
        if amount > Decimal(str(settings.ecommerce_wallet_max_add_fund)):
            raise AppError(400, "Amount above maximum add-fund limit", "amount_too_high")

        payment = EcommercePaymentRequest(
            owner_id=customer.id,
            is_guest=False,
            payment_amount=amount,
            currency_code="UGX",
            purpose=EcommercePaymentPurpose.WALLET_TOPUP,
            payer_information=PesapalService.payer_json(
                customer.email,
                f"{customer.first_name} {customer.last_name}",
                customer.phone,
            ),
            additional_data=json.dumps({"customer_id": str(customer.id)}),
        )
        db.add(payment)
        await db.flush()
        return payment

    @staticmethod
    async def credit_admin_fund(
        db: AsyncSession,
        customer_id: UUID,
        amount: Decimal,
        reference: str = "admin_credit",
    ) -> EcommerceWalletTransaction:
        return await EcommerceWalletService._apply_transaction(
            db,
            customer_id,
            credit=amount,
            transaction_type=EcommerceWalletTransactionType.ADD_FUND_BY_ADMIN,
            reference=reference,
            payment_method="admin",
        )

    @staticmethod
    async def refund_order(
        db: AsyncSession,
        customer_id: UUID,
        amount: Decimal,
        order_public_id: str,
    ) -> EcommerceWalletTransaction:
        return await EcommerceWalletService._apply_transaction(
            db,
            customer_id,
            credit=amount,
            transaction_type=EcommerceWalletTransactionType.ORDER_REFUND,
            reference=f"refund:{order_public_id}",
            payment_method="wallet",
        )

    @staticmethod
    async def fulfill_topup(
        db: AsyncSession,
        payment: EcommercePaymentRequest,
        transaction_ref: str,
    ) -> None:
        if payment.is_paid:
            return
        if payment.purpose != EcommercePaymentPurpose.WALLET_TOPUP:
            raise AppError(400, "Invalid payment purpose", "invalid_payment")
        await EcommerceWalletService.credit_add_fund(
            db,
            payment.owner_id,
            payment.payment_amount,
            payment_method=payment.payment_method,
        )
        payment.is_paid = True
        payment.transaction_id = transaction_ref
        await db.flush()

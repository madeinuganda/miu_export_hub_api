from __future__ import annotations

from pydantic import BaseModel, Field


class PaymentMilestoneView(BaseModel):
    amount: str
    status: str = Field(description="One of: received, pending_delivery, released")


class SupplierPaymentRow(BaseModel):
    orderId: str
    date: str
    product: str
    buyer: str
    totalValue: str
    upfront: PaymentMilestoneView
    balance: PaymentMilestoneView


class SupplierPaymentsSummary(BaseModel):
    totalReceived: str
    totalReceivedHint: str
    pendingOnDelivery: str
    pendingOnDeliveryHint: str
    inEscrow: str
    inEscrowHint: str


class SupplierPaymentsListResponse(BaseModel):
    items: list[SupplierPaymentRow]
    tradeAssurance: dict


class ExportHubPaymentInitResponse(BaseModel):
    redirect_link: str
    payment_id: str
    order_id: str

from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    BUYER = "buyer"
    SUPPLIER = "supplier"
    ADMIN = "admin"


class Platform(str, enum.Enum):
    """Logical product boundary — tokens and RBAC are scoped to a platform."""

    EXPORT_HUB = "export_hub"
    ECOMMERCE = "ecommerce"


class ExportHubAccountType(str, enum.Enum):
    BUYER = "buyer"
    SUPPLIER = "supplier"
    ADMIN = "admin"


class EcommerceAccountType(str, enum.Enum):
    CUSTOMER = "customer"
    SELLER = "seller"
    ADMIN = "admin"
    DELIVERY = "delivery"


class CustomerType(str, enum.Enum):
    """Retail customer segment (mirrors made-in-uganda-web customer_type)."""

    RETAIL = "retail"
    SHOP = "shop"


class OrgMemberRole(str, enum.Enum):
    OWNER = "owner"
    MEMBER = "member"


class VerificationStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING = "pending"
    ACTION_REQUIRED = "action_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class ProductStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class StockStatus(str, enum.Enum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"


class RfqStatus(str, enum.Enum):
    AWAITING = "awaiting"
    RESPONDED = "responded"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class QuoteStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class OrderStatus(str, enum.Enum):
    ORDER_PLACED = "order_placed"
    PAYMENT_SECURED = "payment_secured"
    IN_PRODUCTION = "in_production"
    QUALITY_CHECK = "quality_check"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    FULFILLED = "fulfilled"


class MilestoneState(str, enum.Enum):
    UPCOMING = "upcoming"
    CURRENT = "current"
    COMPLETE = "complete"


class EscrowStatus(str, enum.Enum):
    PENDING = "pending"
    UPFRONT_RECEIVED = "upfront_received"
    BALANCE_RELEASED = "balance_released"


class PaymentMilestoneStatus(str, enum.Enum):
    PENDING = "pending"
    RECEIVED = "received"
    RELEASED = "released"


class ConversationType(str, enum.Enum):
    BUYER_MIU = "buyer_miu"
    SUPPLIER_MIU = "supplier_miu"


class SenderRole(str, enum.Enum):
    BUYER = "buyer"
    SUPPLIER = "supplier"
    ADMIN = "admin"
    SYSTEM = "system"


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CertificationStatus(str, enum.Enum):
    VERIFIED = "verified"
    EXPIRED = "expired"
    PENDING_REVIEW = "pending_review"


class EcommerceProductStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class EcommerceDiscountType(str, enum.Enum):
    PERCENT = "percent"
    FLAT = "flat"


class EcommerceCategoryPosition(str, enum.Enum):
    ROOT = "root"
    SUB = "sub"
    SUB_SUB = "sub_sub"


class EcommerceBannerResourceType(str, enum.Enum):
    PRODUCT = "product"
    CATEGORY = "category"
    SHOP = "shop"
    URL = "url"


class EcommerceOrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELED = "canceled"
    FAILED = "failed"
    RETURNED = "returned"


class EcommercePaymentStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class EcommercePaymentMethod(str, enum.Enum):
    CASH_ON_DELIVERY = "cash_on_delivery"
    PESAPAL = "pesapal"
    OFFLINE = "offline_payment"
    WALLET = "pay_by_wallet"

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import require_customer_password_changed, require_seller_password_changed
from app.core.shared.database import get_db
from app.models.ecommerce.accounts import CustomerAccount, SellerAccount
from app.schemas.ecommerce.review import ReviewCreateRequest
from app.schemas.ecommerce.seller_product import (
    SellerProductCreateRequest,
    SellerProductUpdateRequest,
    SellerStockUpdateRequest,
)
from app.services.ecommerce.notification_service import EcommerceNotificationService
from app.services.ecommerce.review_service import EcommerceReviewService
from app.services.ecommerce.seller_product_service import EcommerceSellerProductService

router = APIRouter()


@router.get("/seller/products")
async def seller_list_products(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(1, ge=1),
    seller: SellerAccount = Depends(require_seller_password_changed),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceSellerProductService.list_products(
        db, seller, limit=limit, offset=offset
    )


@router.post("/seller/products")
async def seller_create_product(
    data: SellerProductCreateRequest,
    seller: SellerAccount = Depends(require_seller_password_changed),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceSellerProductService.create_product(db, seller, data)
    await db.commit()
    return result


@router.put("/seller/products/{product_id}")
async def seller_update_product(
    product_id: UUID,
    data: SellerProductUpdateRequest,
    seller: SellerAccount = Depends(require_seller_password_changed),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceSellerProductService.update_product(db, seller, product_id, data)
    await db.commit()
    return result


@router.put("/seller/products/{product_id}/stock")
async def seller_update_stock(
    product_id: UUID,
    data: SellerStockUpdateRequest,
    seller: SellerAccount = Depends(require_seller_password_changed),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceSellerProductService.update_stock(db, seller, product_id, data)
    await db.commit()
    return result


@router.get("/products/{product_id}/reviews")
async def list_product_reviews(
    product_id: UUID,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceReviewService.list_product_reviews(
        db, product_id, limit=limit, offset=offset
    )


@router.post("/customer/reviews")
async def submit_review(
    data: ReviewCreateRequest,
    account: CustomerAccount = Depends(require_customer_password_changed),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceReviewService.submit_review(db, account, data)
    await db.commit()
    return result


@router.get("/customer/notifications")
async def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(1, ge=1),
    account: CustomerAccount = Depends(require_customer_password_changed),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceNotificationService.list_notifications(
        db, account.id, limit=limit, offset=offset
    )


@router.put("/customer/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: UUID,
    account: CustomerAccount = Depends(require_customer_password_changed),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceNotificationService.mark_read(db, account.id, notification_id)
    await db.commit()
    return result


@router.put("/customer/notifications/read-all")
async def mark_all_notifications_read(
    account: CustomerAccount = Depends(require_customer_password_changed),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceNotificationService.mark_all_read(db, account.id)
    await db.commit()
    return result

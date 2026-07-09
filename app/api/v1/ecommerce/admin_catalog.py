from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.database import get_db
from app.core.shared.rbac_deps import require_ecommerce_permission
from app.models.ecommerce.accounts import EcommerceAdminAccount
from app.schemas.ecommerce.admin import (
    AdminProductCreateRequest,
    AdminProductUpdateRequest,
    AdminWalletCreditRequest,
    BannerCreateRequest,
    BannerUpdateRequest,
    BrandCreateRequest,
    BrandUpdateRequest,
    CategoryCreateRequest,
    CategoryUpdateRequest,
    CouponCreateRequest,
    CouponUpdateRequest,
    ShopShippingMethodRequest,
    VendorCreateRequest,
    VendorUpdateRequest,
)
from app.services.ecommerce.admin_catalog_service import EcommerceAdminCatalogService
from app.services.ecommerce.admin_vendor_service import EcommerceAdminVendorService
from app.services.ecommerce.wallet_service import EcommerceWalletService

router = APIRouter(prefix="/admin")


@router.get("/categories")
async def list_categories(
    _: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.products.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceAdminCatalogService.list_categories(db)


@router.post("/categories")
async def create_category(
    data: CategoryCreateRequest,
    admin: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.products.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAdminCatalogService.create_category(db, data, admin.id)
    await db.commit()
    return result


@router.put("/categories/{category_id}")
async def update_category(
    category_id: UUID,
    data: CategoryUpdateRequest,
    admin: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.products.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAdminCatalogService.update_category(db, category_id, data, admin.id)
    await db.commit()
    return result


@router.get("/brands")
async def list_brands(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(1, ge=1),
    _: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.products.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceAdminCatalogService.list_brands(db, limit=limit, offset=offset)


@router.post("/brands")
async def create_brand(
    data: BrandCreateRequest,
    admin: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.products.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAdminCatalogService.create_brand(db, data, admin.id)
    await db.commit()
    return result


@router.put("/brands/{brand_id}")
async def update_brand(
    brand_id: UUID,
    data: BrandUpdateRequest,
    admin: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.products.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAdminCatalogService.update_brand(db, brand_id, data, admin.id)
    await db.commit()
    return result


@router.get("/products")
async def list_products(
    shop_id: UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(1, ge=1),
    _: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.products.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceAdminCatalogService.list_products(
        db, shop_id=shop_id, limit=limit, offset=offset
    )


@router.post("/products")
async def create_product(
    data: AdminProductCreateRequest,
    admin: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.products.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAdminCatalogService.create_product(db, data, admin.id)
    await db.commit()
    return result


@router.put("/products/{product_id}")
async def update_product(
    product_id: UUID,
    data: AdminProductUpdateRequest,
    admin: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.products.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAdminCatalogService.update_product(db, product_id, data, admin.id)
    await db.commit()
    return result


@router.get("/banners")
async def list_banners(
    _: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.promotions.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceAdminCatalogService.list_banners(db)


@router.post("/banners")
async def create_banner(
    data: BannerCreateRequest,
    admin: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.promotions.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAdminCatalogService.create_banner(db, data, admin.id)
    await db.commit()
    return result


@router.put("/banners/{banner_id}")
async def update_banner(
    banner_id: UUID,
    data: BannerUpdateRequest,
    admin: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.promotions.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAdminCatalogService.update_banner(db, banner_id, data, admin.id)
    await db.commit()
    return result


@router.get("/coupons")
async def list_coupons(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(1, ge=1),
    _: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.promotions.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceAdminCatalogService.list_coupons(db, limit=limit, offset=offset)


@router.post("/coupons")
async def create_coupon(
    data: CouponCreateRequest,
    admin: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.promotions.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAdminCatalogService.create_coupon(db, data, admin.id)
    await db.commit()
    return result


@router.put("/coupons/{coupon_id}")
async def update_coupon(
    coupon_id: UUID,
    data: CouponUpdateRequest,
    admin: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.promotions.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAdminCatalogService.update_coupon(db, coupon_id, data, admin.id)
    await db.commit()
    return result


@router.get("/vendors")
async def list_vendors(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(1, ge=1),
    _: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.vendors.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceAdminVendorService.list_vendors(db, limit=limit, offset=offset)


@router.post("/vendors")
async def create_vendor(
    data: VendorCreateRequest,
    admin: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.vendors.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAdminVendorService.create_vendor(db, data, admin.id)
    await db.commit()
    return result


@router.put("/vendors/{seller_id}")
async def update_vendor(
    seller_id: UUID,
    data: VendorUpdateRequest,
    admin: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.vendors.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAdminVendorService.update_vendor(db, seller_id, data, admin.id)
    await db.commit()
    return result


@router.get("/shops/{shop_id}/shipping-methods")
async def list_shop_shipping(
    shop_id: UUID,
    _: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.vendors.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceAdminVendorService.list_shop_shipping(db, shop_id)


@router.post("/shops/{shop_id}/shipping-methods")
async def upsert_shop_shipping(
    shop_id: UUID,
    data: ShopShippingMethodRequest,
    admin: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.vendors.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAdminVendorService.upsert_shop_shipping(db, shop_id, data, admin.id)
    await db.commit()
    return result


@router.post("/wallet/credit")
async def admin_wallet_credit(
    data: AdminWalletCreditRequest,
    _: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.customers.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceWalletService.credit_admin_fund(
        db, data.customer_id, data.amount, reference=data.reference
    )
    await db.commit()
    return {
        "transaction_id": str(result.id),
        "balance_after": float(result.balance_after),
        "message": "Wallet credited",
    }

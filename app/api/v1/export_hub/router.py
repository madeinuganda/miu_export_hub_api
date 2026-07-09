from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.export_hub import admin, auth, buyer, buyer_onboarding, payments, public, supplier

router = APIRouter(prefix="/export-hub")

router.include_router(auth.router, tags=["Export Hub · Auth"])
router.include_router(public.router, tags=["Export Hub · Public"])
router.include_router(buyer_onboarding.router, tags=["Export Hub · Buyer Onboarding"])
router.include_router(buyer.router, tags=["Export Hub · Buyer"])
router.include_router(supplier.router, tags=["Export Hub · Supplier"])
router.include_router(admin.router, tags=["Export Hub · Admin"])
router.include_router(payments.router, tags=["Export Hub · Payments"])

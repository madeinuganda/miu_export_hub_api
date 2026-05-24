from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import admin, auth, buyer, buyer_onboarding, notifications, public, supplier

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(public.router)
api_router.include_router(buyer_onboarding.router)
api_router.include_router(buyer.router)
api_router.include_router(supplier.router)
api_router.include_router(admin.router)
api_router.include_router(notifications.router)

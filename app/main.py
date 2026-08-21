from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError, app_error_handler, validation_error_handler

settings = get_settings()

OPENAPI_TAGS = [
    {"name": "Export Hub · Auth", "description": "B2B authentication"},
    {"name": "Export Hub · Public", "description": "B2B public marketplace content"},
    {"name": "Export Hub · Buyer Onboarding", "description": "Buyer registration and verification"},
    {"name": "Export Hub · Buyer", "description": "Buyer accounts, RFQs, and orders"},
    {"name": "Export Hub · Supplier", "description": "Supplier accounts and catalog"},
    {"name": "Export Hub · Admin", "description": "Export Hub back-office"},
    {"name": "E-Commerce · Auth", "description": "Retail customer, seller, and shop admin auth"},
    {"name": "E-Commerce · Catalog", "description": "Products, categories, brands"},
    {"name": "E-Commerce · Cart", "description": "Shopping cart"},
    {"name": "E-Commerce · Checkout", "description": "Checkout preview"},
    {"name": "E-Commerce · Shipping", "description": "Shipping method selection"},
    {"name": "E-Commerce · Orders", "description": "Customer orders and payments"},
    {"name": "E-Commerce · Coupons", "description": "Coupon apply and list"},
    {"name": "E-Commerce · Wallet", "description": "Customer wallet balance and top-up"},
    {"name": "E-Commerce · Addresses", "description": "Guest and customer shipping addresses"},
    {"name": "E-Commerce · Seller", "description": "Vendor order management"},
    {"name": "E-Commerce · Admin", "description": "Shop admin orders, catalog, vendors, wallet"},
    {"name": "E-Commerce · Reviews & Notifications", "description": "Product reviews and customer notifications"},
    {"name": "Shared · Platforms", "description": "Platform discovery"},
    {"name": "Shared · Notifications", "description": "Cross-platform notifications"},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path(settings.storage_path).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="MIU Unified API",
    description=(
        "Made in Uganda unified backend — **Export Hub** (B2B) and **E-Commerce** (retail).\n\n"
        "Accounts, JWTs, and RBAC are scoped by `platform` (`export_hub` | `ecommerce`). "
        "Export Hub tokens must not be used on e-commerce routes and vice versa.\n\n"
        "**Authentication:** send JWTs in the `Authorization` header.\n"
        "- Protected routes: `Authorization: Bearer <access_token>`\n"
        "- Refresh/logout: `Authorization: Bearer <refresh_token>`\n\n"
        "**Route prefixes:**\n"
        "- `/api/v1/export-hub/*` — B2B export marketplace\n"
        "- `/api/v1/ecommerce/*` — retail marketplace\n"
        "- Legacy export hub paths remain at `/api/v1/auth/*`, `/api/v1/buyer/*`, etc."
    ),
    version="0.2.0",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
    swagger_ui_parameters={"persistAuthorization": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.include_router(api_router)

uploads_path = Path(settings.storage_path)
uploads_path.mkdir(parents=True, exist_ok=True)


def _resolve_upload_file(file_path: str) -> Path | None:
    """Resolve a stored upload path, blocking directory traversal."""
    try:
        candidate = (uploads_path / file_path).resolve()
        root = uploads_path.resolve()
        candidate.relative_to(root)
        if not candidate.is_file():
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate


@app.get("/api/uploads/{file_path:path}", include_in_schema=False)
async def serve_api_upload(file_path: str):
    """Serve uploads under ``/api/uploads`` for proxies that only forward ``/api``.

    Prefer an explicit route over ``StaticFiles`` mounted at ``/api/uploads`` —
    some Starlette/uvicorn combinations 404 that mount even when the file exists.
    """
    from fastapi.responses import FileResponse

    resolved = _resolve_upload_file(file_path)
    if resolved is None:
        raise AppError(404, "File not found", "not_found")
    return FileResponse(resolved)


# Keep /uploads for older stored URLs and local tooling.
app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "miu-api"}

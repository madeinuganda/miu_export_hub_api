from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError, app_error_handler, validation_error_handler

settings = get_settings()


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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "miu-api"}

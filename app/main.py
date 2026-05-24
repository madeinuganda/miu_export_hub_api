from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler, validation_error_handler

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path(settings.storage_path).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="MIU Export Hub API",
    description=(
        "Made in Uganda Export Hub — B2B export marketplace backend.\n\n"
        "**Authentication:** send JWTs in the `Authorization` header, not query params.\n"
        "- Protected routes: `Authorization: Bearer <access_token>`\n"
        "- `/auth/refresh` and `/auth/logout`: `Authorization: Bearer <refresh_token>`"
    ),
    version="0.1.0",
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

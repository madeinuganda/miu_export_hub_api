from __future__ import annotations

from fastapi import Depends
from app.core.shared.security_schemes import BearerCredentials, http_bearer, http_bearer_refresh


async def get_bearer_token(credentials: BearerCredentials | None = Depends(http_bearer)) -> str:
    from app.core.shared.exceptions import AppError

    if not credentials or credentials.scheme.lower() != "bearer":
        raise AppError(401, "Missing or invalid Authorization header", "unauthorized")
    return credentials.credentials


async def get_optional_bearer_token(
    credentials: BearerCredentials | None = Depends(http_bearer),
) -> str | None:
    if not credentials or credentials.scheme.lower() != "bearer":
        return None
    return credentials.credentials


async def get_refresh_bearer_token(
    credentials: BearerCredentials | None = Depends(http_bearer_refresh),
) -> str:
    from app.core.shared.exceptions import AppError

    if not credentials or credentials.scheme.lower() != "bearer":
        raise AppError(401, "Missing or invalid Authorization header (refresh token)", "unauthorized")
    return credentials.credentials

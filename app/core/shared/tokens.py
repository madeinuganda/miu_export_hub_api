from __future__ import annotations

from uuid import UUID

from app.core.shared.exceptions import AppError
from app.core.shared.security import decode_access_token, decode_token_context
from app.models.shared.enums import Platform


def decode_realm_account_id(
    token: str,
    expected_type: str,
    *,
    expected_platform: str,
    legacy_missing_platform: bool = False,
) -> UUID:
    ctx = decode_token_context(
        token,
        expected_platform=expected_platform,
        expected_account_type=expected_type,
    )
    if ctx:
        return ctx.account_id

    if legacy_missing_platform and expected_platform == Platform.EXPORT_HUB.value:
        payload = decode_access_token(token)
        if payload and payload.get("account_type") == expected_type and not payload.get("platform"):
            return UUID(payload["sub"])
        if expected_type == "admin" and payload and payload.get("account_type") in ("buyer", "supplier"):
            raise AppError(403, "Admin access required", "forbidden")

    raise AppError(401, "Invalid or expired token", "unauthorized")

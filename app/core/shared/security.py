from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.shared.config import get_settings
from app.models.shared.enums import Platform

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


@dataclass(frozen=True)
class TokenContext:
    account_id: UUID
    account_type: str
    platform: str


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(
    account_id: UUID,
    account_type: str,
    *,
    platform: str = Platform.EXPORT_HUB.value,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_expire_minutes)
    payload = {
        "sub": str(account_id),
        "account_type": account_type,
        "platform": platform,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def generate_temporary_password(length: int = 14) -> str:
    """Human-readable temp password for admin invites (excludes ambiguous chars)."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def decode_token_context(
    token: str,
    *,
    expected_platform: str | None = None,
    expected_account_type: str | None = None,
) -> TokenContext | None:
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        return None
    platform = payload.get("platform") or Platform.EXPORT_HUB.value
    account_type = payload.get("account_type")
    if not account_type:
        return None
    if expected_platform and platform != expected_platform:
        return None
    if expected_account_type and account_type != expected_account_type:
        return None
    try:
        account_id = UUID(payload["sub"])
    except (TypeError, ValueError):
        return None
    return TokenContext(account_id=account_id, account_type=account_type, platform=platform)

"""Shared MIU Export Hub branding constants and logo asset."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

BRANDING_DIR = Path(__file__).resolve().parents[2] / "static" / "branding"
LOGO_PATH = BRANDING_DIR / "miu-logo.png"

PRIMARY_HEX = "#19192c"
PRIMARY_RGB = (25, 25, 44)
PRIMARY_DARK_HEX = "#12121f"
PRIMARY_DARK_RGB = (18, 18, 31)


@lru_cache
def logo_bytes() -> bytes | None:
    if LOGO_PATH.is_file():
        return LOGO_PATH.read_bytes()
    return None


@lru_cache
def logo_base64() -> str | None:
    data = logo_bytes()
    if not data:
        return None
    return base64.b64encode(data).decode("ascii")


@lru_cache
def logo_data_uri() -> str | None:
    encoded = logo_base64()
    if not encoded:
        return None
    return f"data:image/png;base64,{encoded}"

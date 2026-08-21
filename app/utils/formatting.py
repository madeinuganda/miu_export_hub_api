from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal


def format_relative_time(value: datetime | None) -> str:
    """Humanize a timestamp as e.g. '2h ago', '3d ago', matching the compact
    style used across RFQ/order inbox listings."""
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - value
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    months = days // 30
    if months < 12:
        return f"{months}mo ago"
    years = months // 12
    return f"{years}y ago"


def format_ugx(amount: Decimal | float | int, per_unit: str | None = None) -> str:
    return format_money(amount, "UGX", per_unit)


# ISO 4217 currencies that do not use minor units in common trade display.
_ZERO_DECIMAL_CURRENCIES = frozenset(
    {
        "UGX",
        "JPY",
        "KRW",
        "VND",
        "CLP",
        "XAF",
        "XOF",
    }
)


def format_money(
    amount: Decimal | float | int,
    currency: str | None = "UGX",
    per_unit: str | None = None,
) -> str:
    code = (currency or "UGX").strip().upper() or "UGX"
    amount_dec = Decimal(str(amount))
    if code in _ZERO_DECIMAL_CURRENCIES:
        formatted = f"{code} {int(amount_dec):,}"
    else:
        quantized = amount_dec.quantize(Decimal("0.01"))
        formatted = f"{code} {quantized:,.2f}"
    if per_unit:
        return f"{formatted}/{per_unit}"
    return formatted


def format_quantity(value: Decimal | float, unit: str) -> str:
    num = float(value)
    if num >= 1000:
        return f"{num:,.0f} {unit}".replace(".0 ", " ")
    return f"{num:g} {unit}"

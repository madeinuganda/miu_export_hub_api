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
    value = int(Decimal(str(amount)))
    formatted = f"UGX {value:,}"
    if per_unit:
        return f"{formatted}/{per_unit}"
    return formatted


def format_quantity(value: Decimal | float, unit: str) -> str:
    num = float(value)
    if num >= 1000:
        return f"{num:,.0f} {unit}".replace(".0 ", " ")
    return f"{num:g} {unit}"

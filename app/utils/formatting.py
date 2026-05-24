from __future__ import annotations

from decimal import Decimal


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

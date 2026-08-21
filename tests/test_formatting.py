from __future__ import annotations

from decimal import Decimal

from app.utils.formatting import format_money, format_ugx


def test_format_ugx_keeps_integer_display():
    assert format_ugx(16095) == "UGX 16,095"
    assert format_ugx(Decimal("16095.99"), "kg") == "UGX 16,095/kg"


def test_format_money_ugx_is_whole_numbers():
    assert format_money(Decimal("2500.75"), "UGX") == "UGX 2,500"
    assert format_money(1000, "ugx", "kg") == "UGX 1,000/kg"


def test_format_money_usd_preserves_minor_units():
    assert format_money(Decimal("16.5"), "USD") == "USD 16.50"
    assert format_money(Decimal("1234.5"), "USD", "kg") == "USD 1,234.50/kg"
    assert format_money(99, "USD") == "USD 99.00"

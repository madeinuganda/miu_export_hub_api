from __future__ import annotations

import enum
from typing import TypeVar

from sqlalchemy import Enum

E = TypeVar("E", bound=enum.Enum)


def str_enum(enum_cls: type[E], name: str, **kwargs) -> Enum:
    """PostgreSQL enum column that persists enum .value (e.g. pending), not .name (PENDING)."""
    return Enum(
        enum_cls,
        name=name,
        values_callable=lambda members: [m.value for m in members],
        **kwargs,
    )

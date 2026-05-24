from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    pages: int


def paginate(items: list[T], page: int = 1, page_size: int = 20) -> PaginatedResponse[T]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    sliced = items[start:end]
    pages = (total + page_size - 1) // page_size if total else 0
    return PaginatedResponse(items=sliced, page=page, page_size=page_size, total=total, pages=pages)

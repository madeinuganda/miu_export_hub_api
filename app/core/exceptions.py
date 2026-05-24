from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(HTTPException):
    def __init__(
        self,
        status_code: int,
        detail: str,
        code: str = "error",
        field_errors: dict[str, list[str]] | None = None,
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
        self.field_errors = field_errors or {}


def problem_response(
    status: int,
    detail: str,
    code: str = "error",
    field_errors: dict[str, list[str]] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {"detail": detail, "code": code}
    if field_errors:
        body["field_errors"] = field_errors
    return JSONResponse(status_code=status, content=body)


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return problem_response(exc.status_code, str(exc.detail), exc.code, exc.field_errors)


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    field_errors: dict[str, list[str]] = {}
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", []) if x != "body")
        field_errors.setdefault(loc or "body", []).append(err.get("msg", "Invalid value"))
    return problem_response(422, "Validation failed", "validation_error", field_errors)

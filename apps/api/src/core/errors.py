from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError


@dataclass
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: Any = None
    headers: dict[str, str] | None = None


def error_payload(code: str, message: str, request_id: str | None, details: Any = None) -> dict[str, Any]:
    return {"code": code, "message": message, "data": None, "details": details, "request_id": request_id}


def _safe_validation_details(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep field diagnostics without reflecting submitted credentials."""

    return [
        {
            "type": error.get("type"),
            "loc": list(error.get("loc", ())),
            "msg": error.get("msg"),
        }
        for error in errors
    ]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_payload(
                "VALIDATION_ERROR",
                "请求参数校验失败",
                getattr(request.state, "request_id", None),
                _safe_validation_details(exc.errors()),
            ),
        )

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, getattr(request.state, "request_id", None), exc.details),
            headers=exc.headers,
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity(request: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_payload("CONFLICT", "数据冲突或重复提交", getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(ValidationError)
    async def handle_validation(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_payload(
                "VALIDATION_ERROR",
                "请求参数校验失败",
                getattr(request.state, "request_id", None),
                _safe_validation_details(exc.errors()),
            ),
        )

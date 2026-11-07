"""Turning errors into ``{"detail", "code"}`` responses (the error types: :mod:`osu_coach.common.errors`)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from osu_coach.common.errors import ApiError


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse({"detail": exc.message, "code": exc.code}, status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(
            {"detail": str(exc.detail), "code": code},
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        parts = []
        for e in exc.errors():
            where = ".".join(str(x) for x in e.get("loc", ()) if x not in ("body", "query", "path"))
            parts.append(f"{where}: {e.get('msg')}" if where else str(e.get("msg")))
        return JSONResponse(
            {"detail": "; ".join(parts) or "Invalid request.", "code": "validation_error"}, status_code=422
        )

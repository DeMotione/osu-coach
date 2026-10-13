"""API errors: every error response is ``{"detail": <message>, "code": <machine-readable code>}``."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorBody(BaseModel):
    detail: str
    code: str


class ApiError(Exception):
    """An error the client can act on, with an HTTP status and a stable ``code``."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class NoProfile(ApiError):
    def __init__(self, message: str = "No replays analysed yet. Scan your replays on the Replays page and press "
                                      "Analyse replays."):
        super().__init__(409, "no_profile", message)


class Busy(ApiError):
    def __init__(self, running: str):
        super().__init__(409, "busy", f"Another task is still running ({running}). Wait until it has finished.")


class NotFound(ApiError):
    def __init__(self, message: str, code: str = "not_found"):
        super().__init__(404, code, message)


class Invalid(ApiError):
    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(422, code, message)


def responses(*statuses: int) -> dict:
    """OpenAPI ``responses`` entry documenting the error body for these statuses."""
    return {s: {"model": ErrorBody} for s in statuses}


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse({"detail": exc.message, "code": exc.code}, status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse({"detail": str(exc.detail), "code": code}, status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        parts = []
        for e in exc.errors():
            where = ".".join(str(x) for x in e.get("loc", ()) if x not in ("body", "query", "path"))
            parts.append(f"{where}: {e.get('msg')}" if where else str(e.get("msg")))
        return JSONResponse({"detail": "; ".join(parts) or "Invalid request.", "code": "validation_error"},
                            status_code=422)

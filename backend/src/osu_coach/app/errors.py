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
    def __init__(
        self, message: str = "No replays analysed yet. Scan your replays on the Replays page and press Analyse replays."
    ):
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


# spelled out: FastAPI's default is the standard library's reason phrase, which changes between Python versions
# (422 is "Unprocessable Entity" up to 3.12, "Unprocessable Content" from 3.13) and with it the OpenAPI document
DESCRIPTIONS = {
    404: "Not found; `code` says what is missing.",
    409: "Not possible right now, e.g. `no_profile` (nothing analysed yet) or `busy` (another task is running).",
    422: "Invalid request: `validation_error` for malformed parameters or body, otherwise a code naming the problem.",
}
_ERROR_BODY_REF = "#/components/schemas/ErrorBody"
_FASTAPI_422_REF = "#/components/schemas/HTTPValidationError"


def responses(*statuses: int) -> dict:
    """OpenAPI ``responses`` entry documenting the error body for these statuses."""
    return {s: {"model": ErrorBody, "description": DESCRIPTIONS[s]} for s in statuses}


def document_validation_errors(schema: dict) -> dict:
    """FastAPI documents request validation errors with its own body (``detail`` as a list), but ``install`` answers
    them with ``ErrorBody`` like every other error: point those responses at it and drop FastAPI's schemas."""
    for operations in schema.get("paths", {}).values():
        for op in operations.values():
            answer = op.get("responses", {}).get("422", {})
            if answer.get("content", {}).get("application/json", {}).get("schema", {}).get("$ref") == _FASTAPI_422_REF:
                op["responses"]["422"] = {
                    "description": DESCRIPTIONS[422],
                    "content": {"application/json": {"schema": {"$ref": _ERROR_BODY_REF}}},
                }
    components = schema.get("components", {}).get("schemas", {})
    for name in ("HTTPValidationError", "ValidationError"):
        components.pop(name, None)
    return schema


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

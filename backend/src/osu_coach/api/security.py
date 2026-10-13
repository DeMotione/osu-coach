"""The API reads and writes files on the player's computer, so only the computer itself may use it.

* ``Host`` must be one of the allowed host names: a web page can't reach the API through a domain that resolves
  to 127.0.0.1 (DNS rebinding).
* Requests that change something (anything but GET / HEAD / OPTIONS) with an ``Origin`` header must come from an
  allowed host: another web site open in the browser can't make the app scan, download or write files (CSRF).
  Requests without ``Origin`` (curl, scripts) are not from a web page and are let through.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _hostname(value: str) -> str | None:
    """Host name of a ``Host`` header (``name[:port]``, ``[v6]:port``) or an origin URL."""
    if not value:
        return None
    try:
        return urlsplit(value if "//" in value else f"//{value}").hostname
    except ValueError:
        return None


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp, allowed_hosts: tuple[str, ...]):
        self.app = app
        self.allowed = {h.strip("[]").lower() for h in allowed_hosts}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if _hostname(headers.get("host", "")) not in self.allowed:
            await self._refuse(send, 400, "invalid_host", "This address isn't allowed; open osu! coach via localhost.")
            return
        origin = headers.get("origin")
        if scope["type"] == "http" and scope.get("method", "GET") not in SAFE_METHODS and origin is not None \
                and _hostname(origin) not in self.allowed:
            await self._refuse(send, 403, "cross_origin", "Requests from other web sites are not allowed.")
            return
        await self.app(scope, receive, send)

    @staticmethod
    async def _refuse(send: Send, status: int, code: str, message: str) -> None:
        body = json.dumps({"detail": message, "code": code}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

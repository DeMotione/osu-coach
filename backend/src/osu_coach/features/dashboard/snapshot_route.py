"""The Analysis pages at start-up, from the last completed analysis (#97).

While the last session is restored, a page that was answered then is answered again from the snapshot at once
(header ``X-Snapshot``: when that analysis ended), instead of 409 "restoring"; every page answered from the profile is
kept for the next start (``Workspace.keep_page``).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

SNAPSHOT_HEADER = "X-Snapshot"


def page_of(request: Request) -> str:
    """The page asked for: the path with its query, the query sorted (the same page asked again is the same)."""
    query = sorted(request.query_params.multi_items())
    return request.url.path + ("?" + "&".join(f"{k}={v}" for k, v in query) if query else "")


class SnapshotRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def route(request: Request) -> Response:
            ws = request.app.state.workspace
            page = page_of(request)
            body = ws.snapshot_page(page)
            if body is not None:
                return JSONResponse(body, headers={SNAPSHOT_HEADER: ws.snapshot_at or ""})
            selection = await run_in_threadpool(ws.page_selection)
            response = await handler(request)
            if response.status_code == 200 and response.media_type == "application/json":
                await run_in_threadpool(ws.keep_page, page, json.loads(response.body), selection)
            return response

        return route

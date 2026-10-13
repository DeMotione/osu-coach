"""Serving the built web app (a single-page app) next to the API."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse

from .errors import NotFound

IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}   # hashed file names (assets/)
REVALIDATE = {"Cache-Control": "no-cache"}                              # index.html, service worker, manifest

NOT_BUILT = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>osu! coach</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><style>
body{font:16px/1.5 system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem;color:#1d1d26;background:#fff}
@media (prefers-color-scheme:dark){body{color:#e8e8f0;background:#16161d}}code{background:rgba(128,128,160,.18);
padding:.1em .35em;border-radius:4px}a{color:#e0408a}</style></head><body><h1>osu! coach API is running</h1>
<p>The web app hasn't been built. In <code>frontend/</code> run <code>npm ci</code> and <code>npm run build</code>,
then restart, or start the dev server with <code>npm run dev</code>.</p>
<p>API reference: <a href="/docs">/docs</a></p></body></html>"""


def mount(app: FastAPI, web_dir: Path | None) -> None:
    """Every path that isn't the API or its docs: a file of the web app, else ``index.html`` (client-side routes)."""
    root = web_dir.resolve() if web_dir else None

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise NotFound(f"No endpoint /{path}.")
        if root is None:
            return HTMLResponse(NOT_BUILT)
        if path:
            f = (root / path).resolve()
            if f.is_file() and root in f.parents:
                return FileResponse(f, headers=IMMUTABLE if f.parent.name == "assets" else REVALIDATE)
        return FileResponse(root / "index.html", headers=REVALIDATE)

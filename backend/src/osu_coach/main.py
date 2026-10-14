"""The FastAPI application: ``create_app()``."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from scalar_fastapi import AgentScalarConfig, get_scalar_api_reference

from osu_coach import __version__
from osu_coach.analyse import routes as analyse
from osu_coach.app import errors, jobs, web
from osu_coach.app.security import LocalOnlyMiddleware
from osu_coach.app.workspace import Workspace
from osu_coach.check import routes as check
from osu_coach.config import Settings, find_web_dir
from osu_coach.dashboard import routes as dashboard
from osu_coach.exports import routes as exports
from osu_coach.library import routes as library
from osu_coach.maps import routes as maps
from osu_coach.progress import routes as progress
from osu_coach.settings import routes as settings
from osu_coach.system import routes as system
from osu_coach.tips import routes as tips

API_PREFIX = "/api"
SCALAR_JS = "https://cdn.jsdelivr.net/npm/@scalar/api-reference@1.71.0"

DESCRIPTION = """
The HTTP API of **osu! coach**: it analyses your own osu!standard replays and tells you what to work on.
It runs on your computer and answers only to it (`localhost`).

### How the pieces fit
1. **Find replays** — `POST /api/library/scan` (osu! installs, folders, uploaded files) runs as a background
   job; poll `GET /api/jobs/{id}`.
2. **Choose and analyse** — `GET /api/library/selection` shows which replays an analysis would read;
   `POST /api/analysis` analyses them (a job). Every analysis is also saved in the progress history.
3. **Read the results** — the `/api/profile/*` pages (Overview, Aim, Tapping, Sliders & Reading, Tips & Setup),
   map suggestions and playlists. They answer `409 no_profile` until something was analysed.

Remembered choices (`/api/settings`, `/api/setup`) are shared with the `osu-coach` command line.

### Conventions
* Rates and shares are fractions (0–1) unless a field says %; `null` means *not enough data*.
* Times are ISO 8601 in UTC.
* Errors are `{"detail": "...", "code": "..."}` with a stable `code`.
"""

TAGS = [
    {"name": "System", "description": "Health and the labels every page uses."},
    {"name": "Settings", "description": "Remembered choices and your setup."},
    {"name": "Replays", "description": "Finding replays and analysing them."},
    {"name": "Jobs", "description": "Progress and results of background work."},
    {"name": "Analysis", "description": "The analysis pages, built from the analysed replays."},
    {"name": "Detailed Map Analysis", "description": "One play on its own."},
    {"name": "Progress & goals", "description": "Your history by month / week / day and skill goals."},
    {"name": "Maps", "description": "Map suggestions and skill playlists from the bundled map pool."},
    {"name": "Get maps into osu!", "description": "collection.db, lazer import folder, .osz downloads."},
]


def create_app(config: Settings | None = None) -> FastAPI:
    config = config or Settings()
    app = FastAPI(
        title="osu! coach API",
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        docs_url=None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if config.api_docs else None,
    )
    app.state.api_docs = config.api_docs
    app.state.workspace = Workspace(config)
    web_dir = config.web_dir if config.web_dir is not None else find_web_dir()
    app.state.web_dir = web_dir if web_dir is not None and (web_dir / "index.html").is_file() else None
    errors.install(app)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(LocalOnlyMiddleware, allowed_hosts=config.allowed_hosts)
    for module in (system, settings, library, analyse, jobs, dashboard, tips, check, progress, maps, exports):
        app.include_router(module.router, prefix=API_PREFIX)
    build_openapi = app.openapi

    def openapi() -> dict:
        return errors.document_validation_errors(build_openapi())  # idempotent; FastAPI caches the document

    app.openapi = openapi  # type: ignore[method-assign]

    if config.api_docs:

        @app.get("/docs", include_in_schema=False)
        def docs() -> HTMLResponse:
            return get_scalar_api_reference(
                openapi_url=app.openapi_url,
                title="osu! coach API",
                scalar_js_url=SCALAR_JS,
                telemetry=False,
                agent=AgentScalarConfig(disabled=True),
                hide_client_button=False,
            )

    web.mount(app, app.state.web_dir)
    return app

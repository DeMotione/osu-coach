# osu! coach backend

Python 3.11+. Organised by feature: every package under `src/osu_coach/` (e.g. `library`, `maps`, `profile`) holds one feature end to end — its pure `domain.py` (a `domain/` package of topic modules when large), disk/network/SQLite code (`repository.py`, parsers), `service.py`, `schemas.py` and `routes.py`. `jobs/` runs background work and `app/` is the web plumbing (`Workspace`, errors, deps, API server, OpenAPI). Entry points: `main.py` (app factory), `cli.py`, `config.py`. Dependencies between features are one-way and enforced by import-linter (`[tool.importlinter]` in `pyproject.toml`).

## Setup

```sh
python -m venv .venv
.venv/Scripts/activate            # Linux/macOS: source .venv/bin/activate
pip install -c ../constraints.txt -e ".[dev]"
```

## Run

```sh
osu-coach-api                     # API on http://127.0.0.1:8501 (docs at /docs)
osu-coach-api --port 9000 --open
osu-coach ui                      # same server, opens the browser
osu-coach analyze                 # CLI report (also: locate, check, playlist, progress)
```

The web app is served at `/` once built (`cd ../frontend && npm run build`); for development run `npm run dev` there.
The server needs a restart after Python changes.

## Test and lint

```sh
pytest
ruff check .
python -m osu_coach.app.openapi ../frontend/src/api/openapi.json   # regenerate API spec
```

## Settings

Environment variables or a `.env` file:

| Variable | Meaning |
|---|---|
| `OSU_COACH_CACHE` | data/cache folder (default: per-user cache dir) |
| `OSU_COACH_WEB_DIR` | built web app folder (default: bundled, or `../frontend/dist`) |

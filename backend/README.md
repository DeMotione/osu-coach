# osu! coach backend

Python 3.11+. Layers under `src/osu_coach/`: `domain/` (analysis logic), `infrastructure/` (`filesystem/`, `http/`, `database/`), `api/` (FastAPI routes), plus `main.py` (app factory) and `config.py`.

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
python -m osu_coach.api.openapi ../frontend/src/api/openapi.json   # regenerate API spec
```

## Settings

Environment variables or a `.env` file:

| Variable | Meaning |
|---|---|
| `OSU_COACH_CACHE` | data/cache folder (default: per-user cache dir) |
| `OSU_COACH_WEB_DIR` | built web app folder (default: bundled, or `../frontend/dist`) |

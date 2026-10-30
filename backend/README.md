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

## Play Goals

`play_goals/` composes lower-level replay checking, map features and player evidence without changing the existing
profile or playlist behavior. `GET /api/play-goals` returns remembered inputs and coverage; `POST /api/play-goals`
starts a cancellable `play_goal` job. Poll the existing job API for its typed result.

Evidence is player-, checksum-, mod- and client-specific. Unknown/custom lazer settings and mismatching simulations
are excluded from forecasts. Failed plays can identify blockers but cannot supply full-map accuracy. Accuracy ranges
need ten completed comparable plays across five maps, capped at two observations per map. These are empirical ranges,
not calibrated probabilities. Missing evidence remains null; practice objectives are separate instructions.

`beatmaps/performance.py` calculates explicit PP scenarios with pinned rosu-pp and conservative hit-result generation.
Broken lazer plays without slider outcomes are rejected. The separate `maps/data/goals_pool.json.gz` contains ranked
map configurations, FC PP samples and calculator/schema provenance; it leaves the original NoMod pool unchanged.

Regenerate the companion data from the repository root:

```sh
python backend/tools/build_goal_pool.py /path/to/public-osu-cache --fetch --count 64
```

The builder selects aim/speed examples across quarter-star bands, verifies downloaded checksums, and produces
deterministic compressed output. `--fetch` downloads only missing public raw maps; omit it to rebuild offline.
The current selection has 62 distinct difficulties, each with eight mod combinations for stable and lazer.
Rebuild after changing calculator versions. Missing/incompatible companion data is an explicit API error.

Goal inputs persist in settings; downloaded targets and versioned target configurations are cached under
`play-goals/` inside the data directory. Job IDs/results are transient and are not restored as fresh assessments.

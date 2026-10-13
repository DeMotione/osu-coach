# AGENTS.md

osu-coach analyzes osu! replays and gives coaching advice. Monorepo: Python 3.11+ FastAPI backend, React 19 + TypeScript (strict) + Vite PWA frontend, Windows packaging (PyInstaller + Inno Setup). The API listens on localhost:8501 only.

## Layout

- `backend/src/osu_coach/` — `domain/` (pure analysis), `infrastructure/` (filesystem, http, sqlite), `api/` (FastAPI routes), plus `main.py`, `cli.py`, `config.py`.
- `backend/tests/` — mirrors the source layout; fixtures in `tests/resources/` (indexed by `index.json`).
- `backend/tools/` — maintenance scripts (pool building, test-data fetching, sim debugging/validation).
- `frontend/src/` — `api/` (typed client, hooks, generated schema), `pages/`, `components/`, `charts/`, `lib/`, `styles/`, `app/`.
- `packaging/` — PyInstaller spec, Inno Setup script, app entry point. `desktop/` — Tauri shell.
- `build/`, `dist/`, `desktop/src-tauri/target/`, `frontend/test-results/` are build output; don't edit.

## Commands

Makefile targets are plain commands (use them or run the equivalents by hand; on Windows run the underlying commands directly).

| Task | Command |
|---|---|
| Install | `pip install -c constraints.txt -e "./backend[dev]"` and `cd frontend && npm ci` |
| API server | `osu-coach-api` (restart after Python changes) |
| Web dev server | `cd frontend && npm run dev` (proxies to :8501) |
| Build web app | `cd frontend && npm run build` |
| Python lint | `cd backend && ruff check . && lint-imports` |
| Web lint | `cd frontend && npm run typecheck && npm run lint` |
| Python tests | `cd backend && python -m pytest` |
| Web unit tests | `cd frontend && npm test` |
| E2E | `cd frontend && npm run build && npm run e2e` (set `OSU_COACH_PYTHON` to the interpreter with osu-coach installed) |
| Regenerate API types | `python -m osu_coach.api.openapi frontend/src/api/openapi.json && cd frontend && npm run gen:api` |

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs Python 3.11 and 3.13, then the web job: API-types check, typecheck, lint, tests, build, e2e.

## Architecture rules

- Layering is enforced by import-linter: `domain` must stay pure (no I/O, no network, no infrastructure imports).
- API errors always use `{"detail": "...", "code": "..."}` with stable codes.
- Rates and shares are 0–1 fractions; `null` means insufficient data. Times are ISO 8601 UTC.
- Long work (scan, analysis, imports, downloads) runs as background jobs polled via `GET /api/jobs/{id}`.

## Generated files

`frontend/src/api/openapi.json` and `frontend/src/api/schema.d.ts` are committed and generated. After any API schema change, regenerate them (see above); never hand-edit. CI and `backend/tests/api/test_openapi_contract.py` fail if they are stale.

## Frontend conventions

- Pages are a single column of blocks: a full-width card, a Row (exactly 2 equal-height children), or Tiles (1/2/3/4/6/8 columns, filling the grid evenly). No empty grid rows, sideways scroll, or card overflow; e2e tests check this at desktop and mobile widths.
- `src/charts/` holds pure ECharts option builders (data + theme in, options out).
- The PWA precaches the app shell but never caches `/api`.

## Testing notes

- `backend/tests/conftest.py` sets `OSU_COACH_NO_AUTODETECT=1` so tests never touch a real osu! install; keep it that way.
- Add backend tests in the matching `tests/{api,domain,infrastructure}` folder; frontend unit tests sit next to the source (`*.test.ts`).

## Environment variables

`OSU_COACH_CACHE` (data dir), `OSU_COACH_WEB_DIR` (built web app to serve), `OSU_COACH_API` (Vite proxy target), `OSU_COACH_PYTHON` (e2e interpreter), `OSU_COACH_NO_AUTODETECT` (skip osu! detection), `OSU_COACH_API_DOCS` (serve `/docs` and show the web app's API link; default true).

## Dependencies and versions

- Python dependencies are pinned in [constraints.txt](constraints.txt); install with `-c constraints.txt`.
- Keep the version (currently 0.9.0) in sync between `backend/pyproject.toml` and `frontend/package.json`.

## Packaging (Windows)

After `cd frontend && npm ci && npm run build`: `python packaging/make_icon.py`, `python -m PyInstaller packaging/osu-coach.spec --noconfirm`, then `ISCC.exe /DAppVersion=<version> packaging/installer.iss`.

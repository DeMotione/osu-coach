# AGENTS.md

osu-coach analyzes osu! replays and gives coaching advice. Monorepo: Python 3.11+ FastAPI backend, React 19 + TypeScript (strict) + Vite PWA frontend, Windows packaging (PyInstaller + Inno Setup). The API listens on localhost:8501 only.

## Layout

- `backend/src/osu_coach/` — one package per feature (e.g. `library`, `maps`, `profile`), plus `jobs/` (background jobs) and `app/` (web plumbing and composition: `Workspace`, errors, deps, `server.py`, `openapi.py`, `session.py` for the analysis run that ties library, progress and profile together), and `main.py`, `cli.py`, `config.py`. The job routes live in `app/jobs.py`, not in `jobs/`: they must know every job kind, and `jobs` is the lowest layer. A feature holds its pure `domain.py` (a `domain/` package of topic modules when it grows, e.g. `profile`), disk/network/SQLite code (`repository.py`, parsers), `service.py`, `schemas.py` and `routes.py` — only those it needs.
- `backend/tests/` — `tests/<feature>/` mirrors the source (`test_domain.py`, `test_repository.py`, `test_routes.py`, plus topic files); fixtures in `tests/resources/` (indexed by `index.json`).
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
| Python lint | `cd backend && ruff check . && ruff format --check . && lint-imports` |
| Python format | `cd backend && ruff format .` |
| Web lint | `cd frontend && npm run typecheck && npm run lint` |
| Python tests | `cd backend && python -m pytest` |
| Web unit tests | `cd frontend && npm test` |
| E2E | `cd frontend && npm run build && npm run e2e` (set `OSU_COACH_PYTHON` to the interpreter with osu-coach installed) |
| Regenerate API types | `python -m osu_coach.app.openapi frontend/src/api/openapi.json && cd frontend && npm run gen:api` |

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs Python 3.11 and 3.13, then the web job: API-types check, typecheck, lint, tests, build, e2e.

## Architecture rules

- Layering is enforced by import-linter (`[tool.importlinter]` in `backend/pyproject.toml`): `*/domain` (module or package; also the judges, curves, features) stays pure — no I/O, network, web or pydantic; services and data code never import routes or `app.workspace`; features depend only downwards (e.g. `profile` may use `analysis`, never `tips`). Feature code names `Workspace` only under `TYPE_CHECKING`. A new feature goes into the `layers` contract. The contract only sees imports: calls made through the `Workspace` (`ws.profile()`, `ws.library`, ...) are not checked, so keep those pointing downwards in review.
- API errors always use `{"detail": "...", "code": "..."}` with stable codes.
- Rates and shares are 0–1 fractions; `null` means insufficient data. Times are ISO 8601 UTC.
- Long work (scan, analysis, imports, downloads) runs as background jobs polled via `GET /api/jobs/{id}`.

## Generated files

`frontend/src/api/openapi.json` and `frontend/src/api/schema.d.ts` are committed and generated. After any API schema change, regenerate them (see above); never hand-edit. CI and `backend/tests/app/test_openapi_contract.py` fail if they are stale.

## Frontend conventions

- Pages are a single column of blocks: a full-width card, a Row (exactly 2 equal-height children), or Tiles (1/2/3/4/6/8 columns, filling the grid evenly). No empty grid rows, sideways scroll, or card overflow; e2e tests check this at desktop and mobile widths.
- `src/charts/` holds pure ECharts option builders (data + theme in, options out).
- The PWA precaches the app shell but never caches `/api`.

## Testing notes

- `backend/tests/conftest.py` sets `OSU_COACH_NO_AUTODETECT=1` so tests never touch a real osu! install; keep it that way.
- Add backend tests in the feature's folder, `tests/<feature>/`; route tests set `pytestmark = pytest.mark.usefixtures("_isolated")` (temporary data folder, no network) and use the `client` / `analysed` fixtures. Frontend unit tests sit next to the source (`*.test.ts`).

## Environment variables

`OSU_COACH_CACHE` (data dir), `OSU_COACH_WEB_DIR` (built web app to serve), `OSU_COACH_API` (Vite proxy target), `OSU_COACH_PYTHON` (e2e interpreter), `OSU_COACH_NO_AUTODETECT` (skip osu! detection), `OSU_COACH_API_DOCS` (serve `/docs` and show the web app's API link; default true), `OSU_COACH_DEMO` (replay folder(s) used when none were saved; for demos).

## Dependencies and versions

- Python dependencies are pinned in [constraints.txt](constraints.txt); install with `-c constraints.txt`.
- Keep the version (currently 0.9.0) in sync between `backend/pyproject.toml`, `backend/src/osu_coach/__init__.py`, `frontend/package.json`, `desktop/package.json`, `desktop/src-tauri/Cargo.toml` and `desktop/src-tauri/tauri.conf.json` (plus their lockfiles). Pushing a tag `v<version>` runs [release.yml](.github/workflows/release.yml), which fails if they differ.

## Packaging (Windows)

After `cd frontend && npm ci && npm run build`: `python packaging/make_icon.py`, `python -m PyInstaller packaging/osu-coach.spec --noconfirm`, then `ISCC.exe /DAppVersion=<version> packaging/installer.iss`.

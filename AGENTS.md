# AGENTS.md

osu-coach analyzes osu! replays and gives coaching advice. Monorepo: Python 3.11+ FastAPI backend, React 19 + TypeScript (strict) + Vite PWA frontend, Windows packaging (PyInstaller server embedded in the Tauri desktop app). The API listens on localhost:8501 only.

## Layout

- `backend/src/osu_coach/` — vertical feature slices on a pure domain, in five layers (each imports only the ones below it):
  - `app/` — composition root: the app factory (`factory.py`), `Workspace` (session state), FastAPI dependencies (`deps.py`), the error responses (`errors.py`), the job routes (`jobs.py`: they must know every job kind), `server.py`, `openapi.py`, `web.py`.
  - `features/<slice>/` — one package per feature slice (`check`, `dashboard`, `exports`, `library`, `maps`, `play_goals`, `progress`, `settings`, `system`, `tips`): `routes.py`, `service.py` (the use-case flow), `schemas.py` (pydantic API models), plus data access only that slice needs (e.g. `maps/variant_repository.py`, `play_goals/repository.py`; `library/session.py` runs the scan and the analysis). Slices never import each other.
  - `infra/` — I/O several slices share: replay and beatmap files (`replays/`, `beatmaps/`), rosu-pp (`beatmaps/difficulty.py`, `performance.py`), the analysis pipeline and cache (`analysis.py`, `library.py`), the per-play summaries (`summaries.py`, SQLite), the map pool (`map_pool.py`, `data/`), `progress.py` (SQLite), `settings.py` (`settings.json`), `session_store.py` (`session.json`), the job runner (`jobs.py`), the clock (`clock.py`: the only place that reads the time; ruff's TID251 bans the direct reads).
  - `common/` — what the slices' HTTP code shares: the error types (`errors.py`, plain exceptions: infra raises them too, and neither knows FastAPI), conversions (`convert.py`), shared response models (`schemas.py`, `jobs.py`, `clicks.py`, `maps.py`, `setup.py`), and the pandas side of the pages: the profile's records as data frames (`frames.py`, built once per profile) and weighted statistics on them (`weighted.py`).
  - `domain/` — pure business calculations by subject (`analysis`, `beatmaps`, `replays`, `player`, `maps`, `progress`, `exports`, `play_goals`, plus `numeric` helpers): no I/O, web, settings, clock or pandas; numbers and typed records in (frozen dataclasses; per-note data as array records on `numeric/arrays.py`), numbers and records out. A play is reduced once to a `PlaySummary` (`domain/player/summary.py`); the profile adds summaries up (`build_profile_from`; `profile_for` is the one the app and the CLI show). `domain/player/` holds the shared profile (`build`, `profile`, `records`, `summary`, `levels`), `measures/` (the per-skill statistics the pages show) and `engines/` (the swappable skill-rating engines: `base` interface, `registry`, what every engine shares (`readiness`, `demand`, `consistency`, `ranking`, `skill_scale`), `comfort/`, `irt/`; the two engines never import each other, and code outside `engines/` reaches them only through it (except `summary.py`). Ask the engine (`uses_level`, `map_scores`, ...) instead of comparing its name).
  - `main.py` (the ASGI app), `cli.py`, `config.py`.
- `backend/tests/` — mirrors the source: `tests/domain/<subject>/`, `tests/infra/`, `tests/features/<slice>/`, `tests/app/`; fixtures in `tests/resources/` (indexed by `index.json`).
- `backend/tools/` — maintenance scripts (pool building, test-data fetching, sim debugging/validation).
- `frontend/src/` — `api/` (typed client, hooks, generated schema), `pages/`, `components/`, `charts/`, `lib/`, `styles/`, `app/`.
- `packaging/` — PyInstaller spec, server zipper, app entry point. `desktop/` — Tauri shell.
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

- Layering is enforced by import-linter (`[tool.importlinter]` in `backend/pyproject.toml`): `app` → `features` → `infra` → `common` → `domain`; feature slices never import each other; inside `domain`, subjects depend only downwards (`maps | progress | exports | play_goals` → `player` → `analysis` → `beatmaps | replays` → `numeric`). `tests/domain/test_purity.py` allow-lists the domain's imports (numpy, scipy and pure standard modules; no pandas) and forbids reading the clock: pass the time, ids and the time zone in (`infra/clock.py`). Something two slices need goes to `domain` (a calculation), `infra` (I/O) or `common` (HTTP models). Slice code names `Workspace` only under `TYPE_CHECKING`; calls through it (`ws.profile()`, `ws.library`, ...) are not checked by the contracts, so keep them pointing downwards in review. Slices read the session through its properties and change it only through its methods (`set_plays`, `set_library`, `open_replay`, ...).
- Stored per-play summaries are keyed by a fingerprint of the compiled `domain` code (`infra/code_fingerprint.py`): changing any domain code makes them again from the analysis cache by itself, with no version to bump. Changing the analysis itself (what the expensive analysis cache holds): bump `ANALYSIS_VERSION`.
- The Star-Scale IRT engine (`domain/player/engines/irt/`) records why it differs from its spec in `docs/star-scale-irt.md` ("Decisions"): when you change how it scores, add or update a decision there with the evidence, and keep "Validation status" honest about what is unfitted.
- API errors always use `{"detail": "...", "code": "..."}` with stable codes; a failed job carries its code too (`code`, next to `error`).
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
- Add backend tests next to their layer: `tests/domain/<subject>/`, `tests/infra/` or `tests/features/<slice>/`; route tests set `pytestmark = pytest.mark.usefixtures("_isolated")` (temporary data folder, no network) and use the `client` / `analysed` fixtures. Frontend unit tests sit next to the source (`*.test.ts`).

## Environment variables

`OSU_COACH_CACHE` (data dir), `OSU_COACH_WEB_DIR` (built web app to serve), `OSU_COACH_API` (Vite proxy target), `OSU_COACH_PYTHON` (e2e interpreter), `OSU_COACH_NO_AUTODETECT` (skip osu! detection), `OSU_COACH_API_DOCS` (serve `/docs` and show the web app's API link; default true), `OSU_COACH_DEMO` (replay folder(s) used when none were saved; for demos).

## Dependencies and versions

- Python dependencies are pinned in [constraints.txt](constraints.txt); install with `-c constraints.txt`.
- Keep the version in sync between `backend/pyproject.toml`, `backend/src/osu_coach/__init__.py`, `frontend/package.json`, `desktop/package.json`, `desktop/src-tauri/Cargo.toml`, `desktop/src-tauri/tauri.conf.json` and `packaging/arch/PKGBUILD` (`pkgver`) (plus their lockfiles). `bash packaging/bump-version.sh <version>` sets all of them and regenerates the OpenAPI document (it carries the version). Pushing a tag `v<version>` runs [release.yml](.github/workflows/release.yml), which fails if they differ.

## Packaging (Windows)

After `cd frontend && npm ci && npm run build`: `python packaging/make_icon.py`, `python -m PyInstaller packaging/osu-coach.spec --noconfirm`, `python packaging/make_server_zip.py`, then `cd desktop && npx tauri build --bundles nsis,msi --features embedded-server`.

Linux (.deb of the Tauri desktop app): `bash packaging/build-deb.sh --no-install` sets up the build (apt packages, Rust, `.venv`) and writes `dist/osu-coach_<version>_amd64.deb`; without `--no-install` it also installs it. A tag `v<version>` builds every installer (Windows setup / msi / portable zip of the Tauri app, Linux deb, and an Arch `.pkg.tar.zst` repackaged from that deb by `packaging/arch/PKGBUILD`) in `release.yml` and publishes them with `packaging/release-notes.md`; pull requests touching `packaging/`, `desktop/` or that workflow build them without publishing.

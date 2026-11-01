# osu! coach — web app

The frontend of osu! coach: a React + TypeScript progressive web app (installable, its shell works offline) that talks
to the API in `../backend`.

| | |
| --- | --- |
| Build | Vite 8, TypeScript 5.9 (strict) |
| UI | React 19, React Router 7, hand-written CSS (design tokens, light / dark) |
| Data | TanStack Query 5, `openapi-fetch` with types generated from the API's OpenAPI document |
| Charts | ECharts 6 (only the parts used are bundled) |
| PWA | `vite-plugin-pwa` (Workbox): manifest, icons, precached app shell; the API is never cached |
| Tests | Vitest + Testing Library (unit), Playwright (end to end, against the real API) |

## Run

The app needs the API. In one terminal (from the repository root, with the Python packages installed):

```
osu-coach-api            # http://localhost:8501
```

In another:

```
cd frontend
npm ci
npm run dev              # http://localhost:5173 — /api and /docs are forwarded to :8501
```

`npm run build` writes `dist/`, which the API serves itself at `/` (`osu-coach ui` opens it).

| Script | |
| --- | --- |
| `npm run typecheck` / `npm run lint` / `npm test` | TypeScript, ESLint, unit tests |
| `npm run e2e` | Builds nothing: run `npm run build` first. Starts the API on :8766 with an empty data folder, analyses the sample replays of the backend tests through the UI and checks every page (set `OSU_COACH_PYTHON` to the Python that has the packages) |
| `npm run gen:api` | Regenerates `src/api/schema.d.ts` from `src/api/openapi.json` (written by `python -m osu_coach.app.openapi src/api/openapi.json`) |

## Layout

```
src/
  api/          client (typed fetch, errors), query hooks, background jobs, generated OpenAPI types
  app/          shell: router, sidebar, query client
  charts/       ECharts wrapper and one module of chart builders per page (pure functions of data + theme)
  components/   UI kit (cards, rows, tiles, controls, states), tables, exports, heat maps
  pages/        one file per page
  lib/          formatting, inline Markdown, theme, hooks
  styles/       tokens (light / dark), base, layout grid, components
```

## Layout rules

The shell stays within the viewport: page content scrolls between the toolbar and status bar, and the sidebar scrolls
independently. Sidebar folding animates its width and labels; reduced-motion preferences disable these transitions.

Every page is one column of blocks as wide as the content area. A block is a full-width card, a row of **two equal
cards** (`<Row>`, which takes exactly two children) or a grid of **equal tiles** (`<Tiles n>`, with `n` in 1, 2, 3, 4,
6, 8 — counts whose columns divide evenly at every width, so no row is half empty). Cards in a row stretch to the same
height, and their charts and tables grow to fill them; when one side has no data it shows an empty state of the same
size instead of leaving a hole. One gap size is used everywhere. The end-to-end tests check these rules on every page
at desktop and phone widths (equal row heights, filled tile grids, no card overflow, no sideways scrolling).

## Play Goals

`/play-goals?tab=fc|farm|mod` is the goal-focused sidebar destination. Its FC tab also accepts `path` (a known/uploaded
replay) or `beatmap` (a difficulty URL/ID), plus `client` and supported `mods`. Replay details and map tables link into it.
Existing analysis and training pages remain available.

Results show five map configurations per page, with a specific objective, evidence strength and optional empirical
accuracy range. PP is shown on the farming tab only, with explicit FC assumptions; a conditional scenario is not a
forecast or an account PP gain. New analyses invalidate the evidence and refresh the assessment. Edits to inputs do
not relabel old results: submit them to generate a new result.

Exports deduplicate map files while retaining mod instructions and objectives in the text map list. A collection
cannot turn mods on. End-to-end coverage lives in `e2e/play-goals.spec.ts`.

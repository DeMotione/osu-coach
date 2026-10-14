# osu! coach

Analyses your own osu!standard replays and tells you what to work on:

- **Statistics** for tapping (unstable rate, timing bias, stream speed, falling behind in streams,
  key alternation and holds), aim (miss causes, over/undershoot, direction, jump distance and angle),
  sliders, reading (AR, dense parts) and consistency.
- **Strong and weak sides.** Each skill gets a score from 0 to 100. 50 means you miss as often as
  expected for how hard those notes are; higher is better.
- **Quadrant analysis.** Shows which screen quadrant you miss in most, checks the difference is
  statistically real, and suggests how to fix it (area placement, arm/wrist reach, practice).
- **Setup tips.** Concrete tablet area or mouse sensitivity changes measured from your jumps (scale,
  rotation, offset), rapid-trigger actuation/sensitivity, offset calibration, key usage.
- **Difficulty weighting.** Your level is detected from your recent replays (comfort star rating, with
  mods such as DT/HR); every replay counts by how close its star rating is to it, so warm-ups on easy maps
  or a 9★ map played for fun don't distort the numbers (see below).
- **Map Suggestion** from a bundled pool of ~5,000 popular ranked maps (1–8.8★, 9 in 10 of them 2–8★,
  the most played per 0.25★ step), each analysed for
  its patterns, with a one-click download of all suggested maps.
- **Skill Development.** Builds a staged playlist (warm-up / core / push) for one skill and gets it into
  the game: for **lazer**, one click makes an import folder with the maps and the collection (see
  below); for **stable**, it adds the collection to your `collection.db` and downloads the maps (.osz).

Everything runs locally. The only network use is downloading beatmaps you don't have, by MD5 from
osu.direct and osu.ppy.sh (verified), and downloading playlist maps from public mirrors.

## Install

Every [release](https://github.com/DeMotione/osu-coach/releases/latest) has these files (none of them needs Python
or Node.js):

| File | Runs on | |
| --- | --- | --- |
| `osu-coach-<version>-setup.exe` | Windows 10 / 11 | **Recommended.** Installs for your user, opens the app in your browser |
| `osu-coach-<version>-x64.msi` | Windows 10 / 11 | The desktop app (its own window), installed for all users |
| `osu-coach-<version>-windows-portable.zip` | Windows 10 / 11 | The desktop app, nothing to install: unzip and start `osu! coach.exe` |
| `osu-coach_<version>_amd64.deb` | Ubuntu 22.04+, Debian 12+ | The desktop app (its own window) |

**Windows setup:** no admin rights needed. It installs for your user, adds a Start menu (and optional desktop)
shortcut, and opens the app in your browser. A small window stays open while osu! coach runs; close it to
quit. Updating = installing a newer setup over it; your settings, replays cache and progress are kept.
The installed `osu-coach.exe` also runs the command line, e.g. `osu-coach.exe analyze --latest 100`.
The installers aren't code-signed yet: if SmartScreen says *Windows protected your PC*, choose **More info → Run
anyway**.

**Linux:** `sudo apt install ./osu-coach_<version>_amd64.deb`, then start **osu! coach** from the app menu
(`sudo apt remove osu-coach` removes it). To build that package from the source code yourself and install it,
run `bash packaging/build-deb.sh` (Debian / Ubuntu / Mint; it sets up everything else it needs). On other
distributions, run it from source (below).

The app is a progressive web app: in Chrome or Edge, *Install osu! coach* in the address bar gives it its own
window and Start menu entry. Its pages open even while osu! coach isn't running and say so until you start it.

osu! coach is open source under the [MIT license](LICENSE).

## Run from source

Windows: double-click `run.bat`. Linux/macOS: `./run.sh`. Both need Python 3.11+, and Node.js 22.12+ to build
the web app once. The first run installs the Python packages into `.venv` and builds the web app, then the app opens
in your browser at http://localhost:8501.

Or manually:

```
python -m venv .venv
.venv/bin/pip install -c constraints.txt -e ./backend     # Windows: .venv\Scripts\pip ...
cd frontend && npm ci && npm run build && cd ..
.venv/bin/osu-coach ui
```

## How the project is built

```
backend/    osu-coach        Python package, organised by feature: each package under src/osu_coach/ (library, maps,
                             profile, progress, ...) holds one feature end to end: pure analysis in `domain.py` (a
                             `domain/` package when large), file / network / SQLite access in `repository.py`, then
                             `service.py`, `schemas.py`, `routes.py`. `app/` is the web plumbing: the HTTP API
                             (FastAPI), API reference with Scalar at /docs, and it serves the built web app. The
                             `osu-coach` command line is `cli.py`
frontend/   osu-coach-web    the web app: React + TypeScript progressive web app (Vite, TanStack Query, ECharts)
desktop/                     the desktop app (Tauri): a window around the web app; makes the .msi and the .deb
packaging/                   frozen server (PyInstaller, embedded in the desktop app), app icons, release notes
```

```
 browser (PWA)  ──HTTP /api──►  backend/…/routes (FastAPI)  ──Python──►  services, domain, repositories
   frontend/                       localhost only                        replays, beatmaps, settings.json,
                                   background jobs                       analysis cache, progress.sqlite
```

* **domain code** (`*/domain.py`) knows nothing about the web. `osu_coach.insights` holds the chart aggregations, so the API only translates.
* **api** keeps the state of the session (scanned library, analysed replays, the profile built from them) in one
  process — osu! coach is a single-user app on your own computer. Slow work (scanning, analysing, downloading) runs
  as background jobs the web app follows. It only answers to `localhost` and refuses requests that change something
  when they come from another web site. Every request and response has a schema; the OpenAPI document is at
  `/api/openapi.json` and the readable reference (Scalar) at http://localhost:8501/docs.
* **frontend** gets its TypeScript types generated from that OpenAPI document, so an API change that breaks the web
  app is a compile error. Layout rule: every page is a column of full-width cards, rows of two equal-height cards
  and grids of equal tiles that always fill their rows (see `frontend/README.md`).

### Development

```
make install        # Python packages (editable) + web app dependencies
make api            # API on :8501           (osu-coach-api)
make web            # web app on :5173, forwarding /api and /docs to :8501
make test lint      # pytest, vitest; ruff, tsc, eslint
make e2e            # build, then drive the app in Chromium against the real API
make openapi        # after changing an API schema: regenerate the web app's types
```

The same commands without `make` are in the `Makefile`; CI (`.github/workflows/ci.yml`) runs all of them, also on
Python 3.11. `constraints.txt` pins the versions everything is tested with.

Building the installers: build the web app (`cd frontend && npm ci && npm run build`), then
`pip install pyinstaller pillow`, `python packaging/make_icon.py`, `python -m PyInstaller packaging/osu-coach.spec
--noconfirm` and `python packaging/make_server_zip.py`. Tauri embeds that frozen server in the desktop app and makes
the setup `.exe`, `.msi`, portable `.exe` and `.deb`: see `desktop/README.md`.

Releasing:

```
bash packaging/bump-version.sh 0.9.2       # every version number + the OpenAPI document; commit it in a pull request
# after the merge, on main:
git tag -a v0.9.2 -m "osu! coach 0.9.2" && git push origin v0.9.2
```

The tag starts the *Release* workflow: it checks that every version number matches the tag, builds every installer,
checks that the portable app and the `.deb` start their server, and publishes them with `packaging/release-notes.md`
as the release notes. Pull requests that change `packaging/`, `desktop/` or that workflow build the installers too,
without publishing.

### Where the replays come from

- **osu!stable**: found automatically (`%LOCALAPPDATA%\osu!`, `C:\osu!`, common Wine prefixes).
  Uses `Data/r` (every local score's replay is saved there automatically) and `Replays`.
- **osu!lazer**: found automatically (`%APPDATA%\osu`, `~/.local/share/osu`, or a moved data
  folder from `storage.ini`). Replays and beatmaps are recognised inside lazer's file store.
- Any folder with `.osr` files, or drag and drop files into the app.

### Playlists in osu!lazer

lazer can't open a `collection.db` by itself, but *Settings → General → Run setup wizard → Import*
("import from a previous osu! version") takes maps **and** collections from any folder that looks like an
osu!stable install. **Make lazer import folder** (Skill Development or Map Suggestion → osu!lazer tab, or
`osu-coach playlist SKILL --lazer`) builds exactly that, in `Downloads/osu-coach lazer import/<playlist>`:

```
osu!.user.cfg      empty: marks the folder as a stable install
collection.db      the playlist
Songs/<set id>/    the maps you don't have yet, downloaded and unpacked
```

Then in lazer: open the setup wizard, press **Next** until **Import**, drag the folder onto the lazer
window (or click *previous osu! install* and pick it) and press **Import content from previous version**.
lazer imports the maps first and the collection after them; re-importing the same playlist only adds
what's new. The folder can be deleted afterwards. *Folder without maps (.zip)* is the same folder with
only the collection, for lazer on another computer.


### Progress by month, week or day

Every analysis is also saved in `progress.sqlite` in the osu! coach data folder, one row per replay, so
the history stays even after replays are deleted. The **Progress** page (or `osu-coach progress`) shows,
per month, ISO week or day (*Group by*), for any date range you pick: plays, maps and maps played for the first time, play time, star rating (comfortable level,
average, hardest clean pass = finished with at most 5 misses per 100 notes, hardest full combo),
accuracy, UR, stream speed and the skills. Monthly skill scores are measured against one miss model
fitted on all your replays — 50 = your all-time average at the same difficulty, higher = fewer misses
than usual that month — and need 5+ plays in a month. Analyse with *All* once to fill in older months;
after that *Latest N* is enough (older analyses are reused from the cache).

### Difficulty weighting and your level

The **Overview** shows *Your level*: the comfort star rating (75% of your finished plays with at most 2 misses
per 100 notes are at or below it) of your replays from the last 30 days before your newest one (at least the
newest 15). Star ratings include the mods of the play (DT, HR, ...). Every replay then gets a weight: **1 within
±0.5★** of your level, then a Gaussian fall-off (σ = 0.5★): 1★ off 61%, 1.5★ 14%, 2★ 1%, 3★ ≈ 0. All statistics
use these weights — miss causes, skill scores, stamina, UR, stream speed, the setup tips (tablet area /
sensitivity, rapid trigger) and the map suggestions. *Set my level by hand* overrides the detected level
(remembered; CLI `--level 6.2`). The Progress page is not weighted, so months stay comparable.

### Calibration on top players' replays

`backend/tools/reference_analysis.py` scores 38 near-perfect plays of top players (WhiteCat, mrekk, chocomint,
MALISZEWSKI, -GN, …; list in `backend/tools/reference_replays.md`, the .osr files go in `backend/tools/reference_replays/`, not in
git) skill by skill. What it changed: **Accuracy** = (300s on single notes − 50%) ÷ 49%, so 100 = 99% 300s (was
95%, which every top player passed: they now spread from ~87 to 99). Aim, flow aim, speed, reading and
consistency compare your misses with what the difficulty predicts; a player who barely misses has nothing to
compare, so those now say **too few misses to tell** instead of *not enough data*. Sliders: top players

### Setup (Tips & Setup page)

- **Aim calibration → your setup**: the over/underaim measured on the Aim page as a tablet area or
  sensitivity change (*keep it* within ±4%), also in the tips list.

- **Aim**: tablet (area width/height and X/Y — OpenTabletDriver values, X/Y = centre of the area) or
  mouse (DPI, sensitivity). With the area known, *Tablet area to try* gives new width/height (from over/
  underaim) and X/Y (from a constant click offset; kept if the offset is too small to matter).
- **Keys**: keyboard, rapid-trigger keyboard (actuation, RT sensitivity) or **SayoDevice keypad** with the
  configurator's settings: Stroke, Trigger, Release, RT Mode, RT Trigger, RT Release, Full Stroke,
  RT Upper Bound, RT Lower Bound. The SayoDevice tip shows *Now → Try* for each, from your tapping
  (double presses, early releases in sliders, falling behind or overlapping keys in streams, presses that
  didn't register) and checks values that don't fit together (Release below Trigger, RT Lower Bound at the
  very bottom of the stroke, ...).

### Command line

```
osu-coach locate                                   # what was found
osu-coach analyze [--folder DIR] [--player NAME]   # full report in the terminal (+ --json)
osu-coach analyze --latest 500                     # only your newest 500 replays (read and analysed)
osu-coach analyze --since 7d --best                # recent form: best plays of the last 7 days (session, 30d, a date)
osu-coach analyze --level 6.2                      # weight replays around 6.2★ instead of the detected level
osu-coach analyze --only a.osr --only b.osr        # only these replay files
osu-coach progress [--player NAME]                 # your progress by month (saved by every analysis)
osu-coach check [REPLAY.osr]                       # one replay on its own (default: your newest)
osu-coach playlist aim --lazer                     # Skill Development: playlist + lazer import folder
osu-coach playlist aim --merge                     # ... added to your osu!stable collections instead
osu-coach playlist speed --comfort 3 --download ~/maps   # without replays: give your level
```

Skills: `aim flow_aim speed stamina accuracy sliders reading consistency quadrant general`.

## How it works

1. **Replay parsing**: `.osr` from stable and lazer, including lazer's extra data.
2. **Judgement re-simulation**: every replay is played back against the exact beatmap with the rules of
   the client that recorded it. Each miss gets a reason: aim, early, late, no tap, lost, or notelock.
   - **osu!stable** (`judge.py`): hit windows, circle radius, notelock, slider follow circle, ticks and
     repeats, stacking and HR/DT/HT/EZ, ported from danser-go and osu!lazer's legacy code. On the test
     set it matches the stored counts exactly on most replays and agrees on 99.6% of judgements.
   - **osu!lazer** (`judge_lazer.py`), ported from lazer's current source: floored hit windows (from
     the June 2025 client on), the hit policy that misses skipped notes, slider tracking with the
     2.4× follow area and the key that hit the head, the tail judged from 36 ms before the end, the
     Classic mod (old slider scoring, note lock), spinners, Difficulty Adjust / Mirror / custom rates,
     and failed plays. On 111 real lazer replays the 300/100/50/miss counts match exactly on 109, and
     all 13 statistics lazer stores (ticks, slider tails, spinner bonus, ...) plus the max combo on 78;
     slider tails are off by 0.1% because live play updates more often than a replay records.
3. **Pattern features** for every note: spacing, angle, direction, quadrant, rhythm snap, streams and
   bursts with their BPM, slider velocity, how many notes are on screen. Local difficulty comes from
   osu!'s own strain model (rosu-pp).
4. **Profile**:
   - Skill scores compare your misses with a model of *your own* miss chance against local difficulty,
     so a weakness means "worse than your level predicts". Hard parts don't count as weaknesses just
     for being hard.
   - Aim calibration fits your actual movement against the needed movement on jumps (affine fit:
     scale x/y, rotation, offset). That fit drives the tablet area and sensitivity advice.
   - *Where your clicks land* (Aim page) draws a random sample of all clicks — the click that hit each
     note and the closest click of each aim miss — **on screen** (shows a constant offset) or **along
     the jump** (rotated so every jump goes right: over/undershoot; a constant offset cancels out there).
     A hit is always inside the circle, so only aim misses land outside it.
   - The quadrant result uses a significance test, so noise isn't reported as a weakness.
5. **Tips and maps** are built from those numbers. Every tip shows the evidence it is based on.
6. **The app** shows all of this on ten pages (Replays, Detailed Map Analysis, Overview, Progress, Aim, Tapping,
   Sliders & Reading, Tips & Setup, Map Suggestion, Skill Development). Light and dark mode follow your system or
   the switch at the bottom of the sidebar, and the charts follow them; pointing at a chart shows its values.

Limitations: lazer replays only record left/right, not which key or mouse button was used, so the
keyboard-vs-mouse-button tip uses stable replays only. Replays from much older lazer clients (e.g. 2022)
were judged with older rules and only match approximately. Tips are heuristics based on your numbers.
Change one setting at a time and re-check after about 20 new replays.

# osu! coach

Analyses your own osu!standard replays and tells you what to work on:

- **Statistics that say the answer first** for tapping (unstable rate, timing bias, stream speed, stamina in long
  streams, key alternation), aim (miss causes, over/undershoot, direction, jump distance and angle, screen quadrant),
  sliders (misses by length and ball speed, why they break) and reading (AR, dense parts). Every chart starts with
  one sentence and its key number, marks what is clearly worse or better than your own average (enough notes that it
  isn't chance), and has a **Practise this** button: a playlist of maps on exactly that weak spot (streams at the BPMs
  where your timing spreads, jumps into the part of the screen you miss, sliders of the length you break, ...).
- **Strong and weak sides.** Eight skills with plain names (Jumps, Spaced streams, Tapping speed, Stamina,
  Accuracy, Sliders, Reading, Consistency), measured one of two ways (Settings → *Skill measurement*):
  **Comfort Score** gives each a score from 0 to 100, where 50 = what maps at your comfort level ask for (assumed
  from ranked maps, not compared with other players); **Star Levels** (experimental) shows each as the map star
  rating it holds up on (see [docs/star-scale-irt.md](docs/star-scale-irt.md)). The Overview, the tips and the
  playlists all name the same strengths and weaknesses.
- **Play Goals**: **FC a map**, **Farm PP**, or **Improve a mod**. Pick a map from your replays (or a replay file or
  beatmap link), see what is stopping your FC, and get focused practice maps. Find map+mod PP opportunities or train
  HD / DT with concrete accuracy objectives.
- **Skill Development**: maps that train your weakest skills, and **Goals & Training**: a staged playlist (warm-up /
  comfort / push) for one skill, with or without mods, from a bundled pool of ~50,000 ranked maps (see below), and
  skill goals to track. Every map is checked against your rating in each skill: one that asks any of them for more
  than half a star beyond your rating (a warm-up: beyond your rating) is left out. One click gets the playlist into
  the game: for **lazer** the maps go straight into lazer and each map opens there from the app; for **stable** it
  adds the collection to your `collection.db` and downloads the maps (.osz).
- **Progress** by month, week or day, kept even after replays are deleted.
- **Setup tips.** Concrete tablet area or mouse sensitivity changes measured from your jumps (scale, rotation,
  offset), rapid-trigger and SayoDevice settings, audio offset, key usage, each with the exact new value.
- **Difficulty weighting.** Your level is detected from your recent replays (comfort star rating, with mods such as
  DT/HR); every replay counts by how close its star rating is to it, so warm-ups on easy maps or a 9★ map played for
  fun don't distort the numbers (see below).

Everything runs locally. The only network use is downloading beatmaps you don't have, by MD5 from osu.direct and
osu.ppy.sh (verified), and downloading playlist maps from public mirrors. Settings → *Missing beatmaps* turns
the beatmap downloads off.

## Install

Every [release](https://github.com/DeMotione/osu-coach/releases/latest) has these files (none of them needs Python
or Node.js):

| File | Runs on | |
| --- | --- | --- |
| `osu-coach-<version>-setup.exe` | Windows 10 / 11 | **Recommended.** The desktop app, installed for your user (no admin rights) |
| `osu-coach-<version>-x64.msi` | Windows 10 / 11 | The same desktop app, installed for all users (also silent: `msiexec /i … /qn`) |
| `osu-coach-<version>-windows-portable.exe` | Windows 10 / 11 | The desktop app without installing it: one file, start it from anywhere |
| `osu-coach_<version>_amd64.deb` | Ubuntu 22.04+, Debian 12+, Linux Mint 21+ | The desktop app |
| `osu-coach-<version>-1-x86_64.pkg.tar.zst` | Arch Linux, Manjaro, EndeavourOS | The same desktop app for pacman |

`SHA256SUMS.txt` lists the checksum of every file.

**Windows:** the setup adds a Start menu (and optional desktop) shortcut. Updating = installing a newer setup over
it; your settings, replay cache and progress are kept. The installers aren't code-signed yet: if SmartScreen says
*Windows protected your PC*, choose **More info → Run anyway**.

**Linux:** `sudo apt install ./osu-coach_<version>_amd64.deb`, then start **osu! coach** from the app menu
(`sudo apt remove osu-coach` removes it). To build that package from the source code yourself and install it, run
`bash packaging/build-deb.sh` (Debian / Ubuntu / Mint; it sets up everything else it needs). On Arch-based
distributions: `sudo pacman -U osu-coach-<version>-1-x86_64.pkg.tar.zst` (`sudo pacman -R osu-coach` removes it),
or `makepkg -si` in `packaging/arch`. On other distributions, run it from source (below).

Run from source, the app is also a progressive web app: in Chrome or Edge, *Install osu! coach* in the address bar
gives it its own window and Start menu entry. Its pages open even while osu! coach isn't running and say so until you
start it.

osu! coach is open source under the [MIT license](LICENSE).

## Run from source

Windows: double-click `run.bat`. Linux/macOS: `./run.sh`. Both need Python 3.11+, and Node.js 22.12+ to build the
web app once. The first run installs the Python packages into `.venv` and builds the web app, then the app opens in
your browser at http://localhost:8501.

Or manually:

```
python -m venv .venv
.venv/bin/pip install -c constraints.txt -e ./backend     # Windows: .venv\Scripts\pip ...
cd frontend && npm ci && npm run build && cd ..
.venv/bin/osu-coach ui
```

## Using it

### First start: the setup guide

The app opens with a five-step guide the first time (a new data folder; anyone with settings from an earlier
version skips it): **osu! version** (stable or lazer, and its folder if it wasn't found), **playstyle** (mouse or
tablet; keyboard, rapid-trigger keyboard or SayoDevice, with the same settings as Setup Tips, where they show
afterwards), **replays** (found automatically or added by hand, then scanned and analysed right away), a **quick
guide** to the sections, and **done**. *Skip setup* closes it for good; the compass button in the toolbar opens it
again. Finished or skipped is `onboarded` in `settings.json`.

### Where the replays come from

- **osu!stable**: found automatically (`%LOCALAPPDATA%\osu!`, `C:\osu!`, common Wine prefixes).
  Uses `Data/r` (every local score's replay is saved there automatically) and `Replays`.
- **osu!lazer**: found automatically (`%APPDATA%\osu`, `~/.local/share/osu`, or a moved data folder from
  `storage.ini`). Replays and beatmaps are recognised inside lazer's file store.
- An osu! folder that wasn't found can be entered in the setup guide or in Settings → *osu! installs*; it is
  remembered (`install_paths` in `settings.json`) and scanned like the others.
- Any folder with `.osr` files, or drag and drop files into the app (Replays page).

### Which replays are analysed

On the Replays page, pick **Latest 100, 500 or 1000**: your newest replays of **the last year** (366 days) are
analysed. Before you start, the page says how long it will take on this computer; while it runs, a screen covers the
app with the progress and the time left. Replays analysed before come from the cache, so the next time is quicker.
When the app starts again, the pages of the last analysis are back at once while the session is restored.
(`OSU_COACH_RECENT_DAYS` changes the one-year window; `0` = any age.)

### New plays, analysed by themselves

While osu! coach is open, it watches the osu! installs that were scanned (`infra/replays/watch.py`). When osu! saves
a replay after a play (stable's `Data/r`, lazer's file store), the replay is added to the library and the analysis
runs again with the Replays page's choices. Only the new play is really analysed; the rest comes from the cache, so
it takes a few seconds. The pages update and a notice links to the play in Detailed Map Analysis. Failed or quit
plays have no replay, so they aren't analysed. Turn it off with *Analyse new plays automatically* on the Replays
page (`auto_analyse` in `settings.json`).

### Difficulty weighting and your level

The **Overview** shows *Your level*: your comfort level, from your replays of the last 30 days before your newest
one (at least the newest 15). Only finished plays with at most 2 misses per 100 notes count: with 3 or more different
map/mod setups among them it is the 75th percentile of each setup's median star rating (*measured*); with fewer it is
a provisional estimate (the 75th percentile of those plays, or without any such play the 25th percentile of all
your star ratings minus 0.4). Star ratings include the mods of the play (DT, HR, ...) and follow osu!'s 2026 star
rating. The skill ratings need a measured comfort level. Every replay then gets a weight: **1 within ±0.5★** of your
level, then a Gaussian fall-off (σ = 0.5★): 1★ off 61%, 1.5★ 14%, 2★ 1%, 3★ ≈ 0. All statistics use these weights —
miss causes, skill scores, stamina, UR, stream speed, the setup tips and the map suggestions. *Set my level by hand*
overrides the detected level under Comfort Score (remembered; CLI `--level 6.2`); Star Levels measures each skill
against the maps themselves and needs none. The Progress page is not weighted, so periods stay comparable.

### The map pool

The bundled pool holds ~50,000 ranked osu!standard difficulties (0.9–13.5★): every one of 6★ and more, and the rest
split evenly between under 5★ and 5–6★, the most played first. Each is analysed for its patterns (streams and their
BPM, jumps, sliders, density, ...) once, when the pool is built (`backend/tools/`), so a playlist needs no download
and no calculation per map. A bundled table holds every pool map with HR, HD and every DT speed from 1.10× to 2.00×
(`infra/data/pool_variants.npz`), and another their PP (`pool_pp.npz`): a playlist with mods or a Play Goals search
takes seconds.

### Playlists for a skill, with or without mods

**Goals & Training → Playlist for a skill** makes a warm-up, a comfort and a push stage for the skill you pick, five
maps at a time (*Other maps* brings up the next five). The playlist stays as you left it when you switch tabs or
start the app again; maps you complete get a check and leave it the next time. **Practise this** on an analysis page
opens it already made for the weak spot found; *Whole skill instead* drops that focus.

In **Fine-tune**, allow Hard Rock, Hidden, and adjustable DT independently. DT rate is an **absolute** playback rate
from 1.10× to 2.00×, inclusive, at 0.01× steps; standard DT is 1.50×. Empty stages show their exclusion reasons,
including missing player ratings and no configurations passing the star and relevance filters. A downloaded
collection or map pack contains beatmaps only; the text list records the exact mods and speed to set in osu!.

For each configuration, the game ruleset model applies HR difficulty caps and vertical reflection, recalculates the
circle radius, scales real-time intervals, durations, BPM, judgement windows and approach time once by the selected
rate, and asks rosu-pp for modified stars and strain sections. Map demands use these transformed features. Reading
demand is an experimental sum of density/pattern demand, low-AR cost below 9.5, high-AR reaction cost above 10.5,
and an extra HD term whose preferred initial AR region is 9.5–10.0. These boundaries and coefficients are
assumptions, not calibrated player thresholds. Suitability `F` is the negative squared star/demand mismatch minus
other-skill overload, plus a history term (the best completed accuracy on the exact map/mod/rate/client
configuration divided by 0.95, capped to 0–1.10; 1 without a matching play); larger is better. `F` is a heuristic
suitability score, not an FC probability or a calibrated performance forecast.

DT/NC replay timing accuracy contributes to the accuracy rating only when its overall replay accuracy is strictly
above 88%; those replays still count for other skills. Too little accepted timing evidence leaves the rating
unmeasured.

### Play a goal, not another chart

Open **Improve → Play Goals**:

- **FC a map**: find the map among all your replays (or give a replay file or a beatmap link) and pick a replay. It
  separates observed miss/slider-break patterns from inferred map demands, gives practice timestamps, and says when a
  target is beyond demonstrated reach.
- **Farm PP** supports NM, HD, HR, DT and their common combinations, over the whole pool. Values are local map PP
  scenarios, **not account PP gains or rank predictions**. Conditional FC PP is clearly distinguished from an
  evidence-supported achievable FC scenario; the app does not promise that you can FC everything it lists.
- **Improve a mod** offers HD or DT maps (any speed from 1.10× to 2.00×) and accuracy/no-break practice objectives.
  With no relevant mod evidence it offers explicitly unassessed starter maps, not an invented HD/DT skill estimate.

Accuracy estimates require at least ten comparable completed plays across five distinct maps, with matching mods and
client. They describe the observed range, not a maximum accuracy or a calibrated FC probability. With insufficient
evidence, the estimate stays unavailable. Useful repeats are allowed: passing a map is not FCing it. Collections
import maps, not mods; apply the displayed mods yourself.

### Playlists in osu!lazer

**Send the maps to lazer** (Goals & Training or Skill Development → osu!lazer tab) downloads the maps you don't have
into osu! coach's data folder (`lazer-maps`) and hands them to lazer's program (`osu!.exe <file.osz>`, found through
the .osz file association lazer registers, else `%LOCALAPPDATA%\osulazer\current`). A running lazer imports them at
once (it waits while you're in gameplay); a closed one starts and imports them. lazer deletes each .osz once it's in,
so nothing is left in Downloads or elsewhere. `osu-coach playlist SKILL --lazer` does the same.

**in lazer**, next to every map in the app, gives lazer the map's link (`osu!.exe osu://b/<beatmap id>`): lazer shows
the map's page with that difficulty picked, and its **Go to beatmap** button (») there opens it in song select.
lazer has no way in from outside straight to song select, and none for collections (only its "import from a previous
osu! version"), so there is no lazer collection: set the mods and speed shown in the list yourself.

### Progress by month, week or day

Every analysis is also saved in `progress.sqlite` in the osu! coach data folder, one row per replay, so the history
stays even after replays are deleted. The **Progress** page (or `osu-coach progress`) shows, per month, ISO week or
day (*Group by*; the last year by week at first), for any date range you pick: plays, maps and maps played for the
first time, play time, star rating (comfortable level, average, hardest clean pass = finished with at most 5 misses
per 100 notes, hardest full combo), accuracy, UR, stream speed, the skills and a calendar of the days you played. The
skills are rated as on the Overview, every period at the same reference, so a rise means you played the skill
better; they need 5+ plays in a period. Periods without plays are gaps on the timeline, not joined by a line.

### Setup Tips page

What to change in your setup, with the exact new value, and what to keep. A change is suggested only when it is
**big enough to feel** and **your misses show it costs you**; otherwise the advice is to keep the setting. A setting
you changed in *Your setup* is checked only on the plays made with it.

- **Tablet area size** (per axis) or **sensitivity** (mouse): only when it moves where you land on your long jumps
  (the longest quarter) by at least 0.2 circle radii, and at least 60% of 30+ misses there land past (or short of)
  the note the way the movement says. The new width / height or sensitivity (and DPI) to set.
- **Tablet area position**: a constant click offset of at least 0.15 circle radii, with your aim misses leaning to
  that side: the new X / Y (OpenTabletDriver values, X / Y = the centre of the area).
- **Tablet area rotation**: when your jumps come out turned enough to move you 0.2 radii on long jumps, and your
  misses lean to that side.
- **Audio offset**: when you hit early (or late) on 70%+ of your plays and centring it wins at least 1% more 300s
  (lazer: the offset change; stable: the Offset wizard). A bias that changes from map to map is timing, a tip.
- **Keys** (keyboard, rapid trigger, SayoDevice): only for keys firing twice (double presses, extra taps), keys
  letting go mid-slider (when it happens often enough to matter) and values the device can't work with.

**Your setup** below holds what you play with (also entered in the setup guide): tablet area width / height and
X / Y or mouse DPI and sensitivity; keyboard, rapid-trigger keyboard (actuation, RT sensitivity) or SayoDevice
keypad (the configurator's Stroke, Trigger, Release, RT Mode, RT Trigger, RT Release, Full Stroke, RT Upper / Lower
Bound). With them, the changes come in millimetres and exact values.

### Command line

```
osu-coach locate                                   # what was found
osu-coach analyze [--folder DIR] [--player NAME]   # full report in the terminal (+ --json)
osu-coach analyze --latest 500                     # only your newest 500 replays (read and analysed)
osu-coach analyze --since 7d --best                # recent form: best plays of the last 7 days (session, 30d, a date)
osu-coach analyze --level 6.2                      # weight replays around 6.2★ instead of the detected level
osu-coach analyze --engine irt                     # skill ratings by Star Levels (default: the one chosen in the app)
osu-coach analyze --only a.osr --only b.osr        # only these replay files
osu-coach progress [--player NAME]                 # your progress by month (saved by every analysis)
osu-coach check [REPLAY.osr]                       # one replay on its own (default: your newest)
osu-coach playlist aim --lazer                     # Goals & Training: playlist, maps sent to lazer
osu-coach playlist aim --merge                     # ... added to your osu!stable collections instead
osu-coach playlist speed --comfort 3 --download ~/maps   # without replays: give your level
```

Skills: `aim flow_aim speed stamina accuracy sliders reading consistency quadrant general`. The command line follows
the app's settings (osu! installs, missing beatmaps, skill measurement).

## How it works

1. **Replay parsing**: `.osr` from stable and lazer, including lazer's extra data.
2. **Judgement re-simulation**: every replay is played back against the exact beatmap with the rules of the client
   that recorded it. Each miss gets a reason: aim, early, late, no tap, lost, or notelock.
   - **osu!stable** (`domain/analysis/judge.py`): hit windows, circle radius, notelock, slider follow circle, ticks
     and repeats, stacking and HR/DT/HT/EZ, ported from danser-go and osu!lazer's legacy code. On the test set it
     matches the stored counts exactly on most replays and agrees on 99.6% of judgements.
   - **osu!lazer** (`domain/analysis/judge_lazer.py`), ported from lazer's current source: floored hit windows (from
     the June 2025 client on), the hit policy that misses skipped notes, slider tracking with the 2.4× follow area
     and the key that hit the head, the tail judged from 36 ms before the end, the Classic mod (old slider scoring,
     note lock), spinners, Difficulty Adjust / Mirror / custom rates, and failed plays. On 111 real lazer replays the
     300/100/50/miss counts match exactly on 109, and all 13 statistics lazer stores (ticks, slider tails, spinner
     bonus, ...) plus the max combo on 78; slider tails are off by 0.1% because live play updates more often than a
     replay records.
3. **Pattern features** for every note: spacing, angle, direction, quadrant, rhythm snap, streams and bursts with
   their BPM, slider length and velocity, how many notes are on screen. Star ratings and local difficulty come from
   osu!'s own model (rosu-pp, with osu!'s 2026 star rating: `vendor/rosu-pp-2026`).
4. **Profile**: each play is reduced once to a summary, and the profile adds them up.
   - Skill ratings compare what you did on each map/mod setup (cursor speed of the jumps you landed, the stream
     speed you tap cleanly, the tempo you keep up, ...) with what is typical at your comfort level (Comfort Score),
     or find the star rating each skill holds up on (Star Levels). A skill your maps never tested at your level gets
     "at least" and what to play instead of a rating.
   - Aim calibration fits your actual movement against the needed movement on jumps (affine fit: scale x/y,
     rotation, offset). That fit drives the tablet area and sensitivity advice.
   - *Where your clicks land* (Aim page) draws a random sample of all clicks — the click that hit each note and the
     closest click of each aim miss — **on screen** (shows a constant offset) or **along the jump** (rotated so every
     jump goes right: over/undershoot; a constant offset cancels out there).
   - A group (a stream speed, a jump distance, an AR, ...) is called clearly worse or better than your average only
     with enough notes that it isn't chance (a significance test), so noise isn't reported as a weakness.
5. **Tips and maps** are built from those numbers. Every tip shows the evidence it is based on.
6. **The app** shows all of this on twelve pages (Replays, Detailed Map Analysis, Overview, Progress, Aim, Tapping,
   Sliders & Reading, Tips, Setup Tips, Skill Development, Goals & Training, Play Goals) and Settings. Light and dark
   mode follow your system or the switch in the toolbar, and the charts follow them; pointing at a chart shows its
   values.

Limitations: lazer replays only record left/right, not which key or mouse button was used, so the
keyboard-vs-mouse-button tip uses stable replays only. Replays from much older lazer clients (e.g. 2022) were judged
with older rules and only match approximately. Tips are heuristics based on your numbers. Change one setting at a
time and re-check after about 20 new replays.

### Calibration on top players' replays

`backend/tools/reference_analysis.py` scores 38 near-perfect plays of top players (WhiteCat, mrekk, chocomint,
MALISZEWSKI, -GN, …; list in `backend/tools/reference_replays.md`, the .osr files go in
`backend/tools/reference_replays/`, not in git) skill by skill with the same skill ratings the Overview shows, plus
the measured values and references behind them, so a yardstick that reads top players too low or too high shows up
before and after a change.

## How the project is built

```
backend/    osu-coach        Python package (FastAPI), in five layers, each importing only the ones below it:
                               app/       the app factory, session state, the job routes, the server
                               features/  one package per feature slice (library, maps, play_goals, progress, ...):
                                          routes.py, service.py, schemas.py
                               infra/     files, SQLite, rosu-pp, the analysis cache, the bundled map pool
                               common/    what the slices' HTTP code shares (errors, response models, data frames)
                               domain/    pure calculations: judging, patterns, the profile, the skill engines,
                                          the map ranking (no I/O, no web, no clock)
                             the `osu-coach` command line is `cli.py`
frontend/   osu-coach-web    the web app: React + TypeScript progressive web app (Vite, TanStack Query, ECharts)
desktop/                     the desktop app (Tauri): a window around the web app, with the server inside
packaging/                   frozen server (PyInstaller, embedded in the desktop app), app icons, release notes
vendor/rosu-pp-2026/         prebuilt wheels of rosu-pp with osu!'s 2026 star rating
```

```
 browser / desktop window ──HTTP /api──►  features/…/routes (FastAPI)  ──►  services ──► infra, domain
   frontend/                                localhost only                      replays, beatmaps, settings.json,
                                            background jobs                     session.json, analysis cache,
                                                                                summaries.sqlite, progress.sqlite
```

* **domain** knows nothing about the web, files or the clock; import-linter (`backend/pyproject.toml`) keeps the
  layers apart and the feature slices from importing each other. [AGENTS.md](AGENTS.md) has the details.
* **the API** keeps the state of the session (scanned library, analysed replays, the profile built from them) in one
  process — osu! coach is a single-user app on your own computer. Slow work (scanning, analysing, downloading,
  searching) runs as background jobs the web app follows. It only answers to `localhost` and refuses requests that
  change something when they come from another web site. Every request and response has a schema; the OpenAPI
  document is at `/api/openapi.json` and the readable reference (Scalar) at http://localhost:8501/docs.
* **frontend** gets its TypeScript types generated from that OpenAPI document, so an API change that breaks the web
  app is a compile error. Layout rule: every page is a column of full-width cards, rows of two equal-height cards
  and grids of equal tiles that always fill their rows (see `frontend/README.md`).

The last scan and the analysed replays are remembered in `session.json`, and the pages of the last analysis in
`snapshot.json.gz`: on the next start the pages are back at once and the session is restored in the background.

### Development

```
make install        # Python packages (editable, with dev tools) + web app dependencies
make api            # API on :8501           (osu-coach-api; restart after Python changes)
make web            # web app on :5173, forwarding /api and /docs to :8501
make test lint      # pytest, vitest; ruff, import layering, tsc, eslint
make openapi        # after changing an API schema: regenerate the web app's types
```

End-to-end tests: `cd frontend && npm run build && npm run e2e` (drives the app in Chromium against the real API;
set `OSU_COACH_PYTHON` to the interpreter with osu-coach installed). The same commands without `make` are in the
`Makefile`; CI (`.github/workflows/ci.yml`) runs all of them on Python 3.11 and 3.13. `constraints.txt` pins the
versions everything is tested with.

Building the installers: build the web app (`cd frontend && npm ci && npm run build`), then
`python packaging/make_icon.py`, `python -m PyInstaller packaging/osu-coach.spec --noconfirm` and
`python packaging/make_server_zip.py`. Tauri embeds that frozen server in the desktop app and makes the setup `.exe`,
`.msi`, portable `.exe` and `.deb`: see `desktop/README.md`.

Releasing:

```
bash packaging/bump-version.sh <version>   # every version number + the OpenAPI document; commit it in a pull request
# after the merge, on main:
git tag -a v<version> -m "osu! coach <version>" && git push origin v<version>
```

The tag starts the *Release* workflow: it checks that every version number matches the tag, builds every installer,
checks that the portable app, the `.deb` and the Arch package start their server, and publishes them with
`packaging/release-notes.md` as the release notes. Pull requests that change `packaging/`, `desktop/` or that
workflow build the installers too, without publishing.

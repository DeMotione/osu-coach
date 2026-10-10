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
- **Map suggestions** from a bundled pool of ~2,700 popular ranked maps (0.8–8.5★), each analysed for
  its patterns.
- **Improve a skill.** Builds a staged playlist (warm-up / core / push) for one skill and gets it into
  the game: for **lazer**, one click makes an import folder with the maps and the collection (see
  below); for **stable**, it adds the collection to your `collection.db` and downloads the maps (.osz).

Everything runs locally. The only network use is downloading beatmaps you don't have, by MD5 from
osu.direct and osu.ppy.sh (verified), and downloading playlist maps from public mirrors.

## Run it

Windows: double-click `run.bat`. Linux/macOS: `./run.sh`. Both need Python 3.11+. The first run
installs the dependencies into `.venv`, then the app opens in your browser.

Or manually:

```
python -m venv .venv
.venv/bin/pip install -e .          # Windows: .venv\Scripts\pip install -e .
.venv/bin/osu-coach ui
```

### Where the replays come from

- **osu!stable**: found automatically (`%LOCALAPPDATA%\osu!`, `C:\osu!`, common Wine prefixes).
  Uses `Data/r` (every local score's replay is saved there automatically) and `Replays`.
- **osu!lazer**: found automatically (`%APPDATA%\osu`, `~/.local/share/osu`, or a moved data
  folder from `storage.ini`). Replays and beatmaps are recognised inside lazer's file store.
- Any folder with `.osr` files, or drag and drop files into the app.

**Replays to read** (above the Scan button): *Latest 100 / 500 / 1000* or *All*. With a limit, the scan
reads replay files newest first and stops as soon as your newest N plays are certain, and only those are
analysed: faster on big installs, and closer to how you play now. Beatmaps are then looked up only for
those replays. "Your" replays = the player name with the most replays on the computer; if you pick another
player and fewer than N turn up, choose *All*. The choice is remembered.

You need **20 or more replays** for useful statistics, and the more the better. Relax, autopilot and
autoplay replays are skipped, and so are lazer replays with mods the simulation can't follow (Wind Up/Down
and Adaptive Speed change the speed mid-map; Random, Wiggle, Magnetised and similar move notes or the
cursor). The app lists every skipped replay with the reason.

### Playlists in osu!lazer

lazer can't open a `collection.db` by itself, but *Settings → General → Run setup wizard → Import*
("import from a previous osu! version") takes maps **and** collections from any folder that looks like an
osu!stable install. **Make lazer import folder** (Improve a skill → osu!lazer tab, or
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

### Progress by month

Every analysis is also saved in `progress.sqlite` in the osu! coach data folder, one row per replay, so
the history stays even after replays are deleted. The **Progress** page (or `osu-coach progress`) shows,
per month: plays, maps and maps played for the first time, play time, star rating (comfortable level,
average, hardest clean pass = finished with at most 5 misses per 100 notes, hardest full combo),
accuracy, UR, stream speed and the skills. Monthly skill scores are measured against one miss model
fitted on all your replays — 50 = your all-time average at the same difficulty, higher = fewer misses
than usual that month — and need 5+ plays in a month. Analyse with *All* once to fill in older months;
after that *Latest N* is enough (older analyses are reused from the cache).

### Setup (Tips & setup page)

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
osu-coach progress [--player NAME]                 # your progress by month (saved by every analysis)
osu-coach playlist aim --lazer                     # playlist + lazer import folder (maps + collection)
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

## Development

```
.venv/bin/pip install -e .[dev]
.venv/bin/python -m pytest                     # tests use real replays in tests/resources
python dev_tools/fetch_pool_raw.py RAW 40 100  # refresh map pool sources (osu.direct)
python dev_tools/build_pool.py RAW             # rebuild osu_coach/data/pool.json.gz
```

Caches, settings and downloaded beatmaps live in the per-user cache folder (`~/.cache/osu-coach`,
`%LOCALAPPDATA%\osu-coach`). Set `OSU_COACH_CACHE` to override. `OSU_COACH_NO_AUTODETECT=1` turns off
the automatic osu! search (the tests set it, so they never read the osu! installs of the computer they
run on).

Limitations: lazer replays only record left/right, not which key or mouse button was used, so the
keyboard-vs-mouse-button tip uses stable replays only. Replays from much older lazer clients (e.g. 2022)
were judged with older rules and only match approximately. Tips are heuristics based on your numbers.
Change one setting at a time and re-check after about 20 new replays.

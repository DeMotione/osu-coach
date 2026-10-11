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
- **Map Suggestion** from a bundled pool of ~2,700 popular ranked maps (0.8–8.5★), each analysed for
  its patterns, with a one-click download of all suggested maps.
- **Skill Development.** Builds a staged playlist (warm-up / core / push) for one skill and gets it into
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

**Played** (next to it): *All time / Last session / Last 7 days / Last 30 days / Custom range* — your recent
form. *Last session* = your newest replay and the ones before it with less than an hour between plays. The
time filter picks the replays before they are analysed; together with *Latest N* the newest N of that time
are used.

**All replays / Best replays** (step 2, remembered; CLI `--best` / `--all-replays`): *Best replays* = only
passed plays (every note reached, no fail), and for each beatmap + speed mod (NM, DT/NC, HT, custom rate) only
your single best play: highest score, ties broken by accuracy. Retries and fails then don't count.

**Only these files**: switch *Analyse* to *Only these files* and drop `.osr` files: only those are analysed,
the rest of your library is ignored (CLI: `--only FILE.osr`, repeatable).

You need **20 or more replays** for useful statistics, and the more the better. Relax, autopilot and
autoplay replays are skipped, and so are lazer replays with mods the simulation can't follow (Wind Up/Down
and Adaptive Speed change the speed mid-map; Random, Wiggle, Magnetised and similar move notes or the
cursor). The app lists every skipped replay with the reason.

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

### Detailed Map Analysis (one replay on its own)

The **Detailed Map Analysis** page shows a single play: it opens on your newest replay (no scan needed), any other
can be picked from the list, a `.osr` file can be dropped in, and on the Replays page a row of *Analysed
replays* opens with **Detailed map analysis**. It shows:

- the result, and the map **as it was played**: BPM, UR, speed (DT/HT or a custom lazer rate such as ×1.26),
  AR / OD / CS / HP with the mods (HR, EZ, Difficulty Adjust, …) and length, plus a few plain sentences on
  what cost the play (misses by reason and pattern, the part of the map where most happened, timing);
- every miss and combo break with its **time in the map in the osu! editor format** (`01:23:456`), why
  it happened (aim — and how far off, overshot / fell short —, too early/late by how many ms, no tap,
  notelock, slider break: cursor left the slider / key released) and on what pattern;
- *Where they cluster — parts to practise*: each cluster of misses as a part of the map to cut out, from a
  measure before the first miss to just after the last one, on whole notes, with its length in seconds and
  notes. Copy those notes into a difficulty of their own in the editor, play it until it's clean, then play
  the whole map again and open the new replay here;
- your timing through the map (every hit, a running average, misses marked) and where your clicks landed;
- **all your plays of this map**: every play in your history and every replay of the map on the computer,
  newest first (pick a row → *Open this play*). Best / not best is judged only against plays with the same
  speed and settings (rate, AR/OD/CS/HP, HD/FL): a DT ×1.5 play at 285 BPM and a ×1.26 play at 240 BPM of
  the same map are different challenges. A replay dropped in or opened from the Replays page switches the
  list to *Only plays of this map*.

The check is saved in the progress history. Command line: `osu-coach check` (newest replay) or
`osu-coach check path/to/replay.osr`.

### Progress by month

Every analysis is also saved in `progress.sqlite` in the osu! coach data folder, one row per replay, so
the history stays even after replays are deleted. The **Progress** page (or `osu-coach progress`) shows,
per month: plays, maps and maps played for the first time, play time, star rating (comfortable level,
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

`dev_tools/reference_analysis.py` scores 38 near-perfect plays of top players (WhiteCat, mrekk, chocomint,
MALISZEWSKI, -GN, …; list in `dev_tools/reference_replays.md`, the .osr files go in `reference_replays/`, not in
git) skill by skill. What it changed: **Accuracy** = (300s on single notes − 50%) ÷ 49%, so 100 = 99% 300s (was
95%, which every top player passed: they now spread from ~87 to 99). Aim, flow aim, speed, reading and
consistency compare your misses with what the difficulty predicts; a player who barely misses has nothing to
compare, so those now say **too few misses to tell** instead of *not enough data*. Sliders: top players
break none (100), so the scale's top end needed no change.

### Miss causes

aim (jumps and single notes at normal speed), **speed-aim** (you tapped in time but the cursor couldn't keep
up: aim misses in bursts / streams of 3+ notes — spaced or not — and on jumps ≤ 125 ms apart), too early / too
late, no tap, lost, notelock. *Why you miss* also compares aim and speed-aim with what the difficulty of those
notes predicts. **Stream speed** (Tapping page) is judged on finger misses only (no tap, early/late, notelock,
lost); speed-aim misses are shown separately on the same chart. **Stamina** (skill score) is how long you keep a high
tempo before your fingers give in, not how accurate you stay. osu!standard has no stamina skill of its own — the
star rating's speed strain decays to 30% per second (lazer `Speed.cs`) — so osu! coach measures it on you, as a
**tempo-duration curve** (`tempo_curve`): for 10 s, 30 s, 1, 2 and 5 minutes, the fastest tempo you kept up in
any stretch of a play that long. Tempo = notes you pressed a key for per second, as 1/4-note BPM (15 × notes per
second, so a 220 BPM stream = 220); 100s, 50s and misses where you tapped count (also overstreaming — tapping
faster than the notes is never a loss), notes without a tap don't. When you start **undertapping** (pressing for
less than 90% of the notes in the stretch; 60% or less = 0, linear between) the tempo stops counting. Each
duration: one value per map, pp-weighted (see above; it counts once 2+ maps were that long);
50 = the typical tempo for your level for that long (120 + 15 × level BPM, e.g. 210 at 6★, × 0.55 / 0.47 / 0.41
/ 0.38 / 0.33 for 10 s … 5 min, since longer stretches always include slower parts); 10% faster ≈ +10 points
(75 per doubling). The score is the average over the durations. Low-tempo marathons stay low and death streams
you can't keep up score low for the long durations. How steady your taps stay in long streams (second half vs
first half, from the key presses) is shown for information. Difficulty weights don't apply here.
**Skill weighting (like osu! pp)**: every skill ranks your plays by how hard they were for that skill (aim, flow
aim, reading: the 80th percentile of the notes' difficulty; accuracy, consistency: star rating) or by the value
reached (speed, stamina, sliders: one value per map, your best play of it); the first counts 100%, each next one
1/N less, N = replays analysed (100 replays: 100%, 99%, 98% …). The other statistics keep the level weighting.
**Jump aim** (`aim_values`, `aim_score`): distance × speed × combo. Per passed play, the average cursor speed
of its 30 fastest jumps / spaced notes (distance in circle diameters ÷ the real time to get there) × (your max
combo ÷ the map's max combo)^0.8, like osu!'s pp; pp-weighted over maps (best pass of each); 50 = 16 circles/s at
full combo at 6★ (×2 every 12★), +25 per doubling. Flow aim and reading stay miss-model scores.
**Tapping speed** (`speed_values`, `speed_score`): per play the 3rd fastest clean burst / stream (3+ notes; no
finger miss — no tap, too early / late, notelock; cursor misses don't count — and 80%+ of its hit notes as 300s);
pp-weighted over maps; 50 = `stamina_ref_bpm` of your level, 75 points per doubling.
**Slider control** counts how hard the sliders are that you follow to the end (`slider_difficulty`): speed
(circle diameters per second) × length (log2 of 1 + the path beyond what the follow circle covers; repeats add)
× shape (+½ per half circle of turning up to 2 turns, +0.3 per sharp corner, +0.2 per left↔right bend, up to 4
each) × speed change (vs the previous slider within 2 s, up to ×2) × rush (up to ×1.5 when the next note comes
< 250 ms after the end). Per play the 30 hardest sliders whose head you hit count: their average × (share held)³;
pp-weighted over maps; score = 50 + 25 × log2(value ÷ typical for your level; 40 at 6★, ×2 every 3★).

*Stamina in long streams* (Tapping page) shows how precise your taps stay through streams of 16+ notes:
the average **absolute** timing error (early and late alike — the plain average cancels them out to ~0) on
notes 1–4, 5–8, … with one line per stream length (16–31, 32–63, 64+ notes). Where it starts to climb is
where your stamina gives in (in notes and seconds at the typical BPM); up to there is your comfortable
stream length, and the page suggests maps whose longest stream is in the comfortable range and in the range
just past it (stamina practice). **Stream speed UR** is measured in each play on its own (the middle play
per 10 BPM, plus your best play): throwing the hits of different plays together mixes their offsets and
gave a higher, misleading UR. A dashed trend line shows the UR your other speeds predict; BPMs clearly
above it are marked as weak spots. *Hit timing* colours each hit by what it scored (300 / 100 / 50).

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
6. **Light and dark mode** follow Streamlit's Settings → theme (or your system); the charts follow it too.
   Charts can't be zoomed by click-and-drag (hover still shows the values), and the sidebar's collapse
   button is always visible.

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

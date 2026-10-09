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
- **Improve a skill.** Builds a staged playlist (warm-up / core / push) for one skill. You can export
  it as a `collection.db` for stable or lazer, add it to your stable collections directly, and
  download the maps (.osz).

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

You need **20 or more replays** for useful statistics, and the more the better. Relax, autopilot and
autoplay replays are skipped.

### Command line

```
osu-coach locate                                   # what was found
osu-coach analyze [--folder DIR] [--player NAME]   # full report in the terminal (+ --json)
osu-coach playlist aim --collection collection.db  # playlist for one skill
osu-coach playlist speed --comfort 3 --download ~/maps   # without replays: give your level
```

Skills: `aim flow_aim speed stamina accuracy sliders reading consistency quadrant general`.

## How it works

1. **Replay parsing**: `.osr` from stable and lazer, including lazer's extra data.
2. **Judgement re-simulation**: every replay is played back against the exact beatmap with osu!stable's
   rules: hit windows, circle radius, notelock, slider follow circle, ticks and repeats, stacking, and
   HR/DT/HT/EZ. Rules are ported from danser-go and osu!lazer's legacy code. Lazer replays use lazer's
   hit policy. The result is checked against the counts stored in the replay. On the test set it matches
   exactly on most replays and agrees on 99.6% of judgements. Each miss gets a reason: aim, early,
   late, no tap, lost, or notelock.
3. **Pattern features** for every note: spacing, angle, direction, quadrant, rhythm snap, streams and
   bursts with their BPM, slider velocity, how many notes are on screen. Local difficulty comes from
   osu!'s own strain model (rosu-pp).
4. **Profile**:
   - Skill scores compare your misses with a model of *your own* miss chance against local difficulty,
     so a weakness means "worse than your level predicts". Hard parts don't count as weaknesses just
     for being hard.
   - Aim calibration fits your actual movement against the needed movement on jumps (affine fit:
     scale x/y, rotation, offset). That fit drives the tablet area and sensitivity advice.
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
`%LOCALAPPDATA%\osu-coach`). Set `OSU_COACH_CACHE` to override.

Limitations: lazer judgement is approximated with stable rules plus lazer's hit policy, so slider
scoring differs slightly. Tips are heuristics based on your numbers. Change one setting at a time and
re-check after about 20 new replays.

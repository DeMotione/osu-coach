# osu-coach: where we stopped (2026-10-10)

## Current state

Everything from the first version (replay/beatmap parsing, judgement re-simulation, statistics, skill
scores, quadrant analysis, tips, map pool, skill playlists, collection export, osu! auto-discovery, CLI and
Streamlit UI), plus:

- **Accurate lazer judgement** (`judge_lazer.py`, ported from lazer's current source): floored hit windows,
  the hit policy that misses skipped notes, slider tracking (2.4× follow area, the key that hit the head),
  tail leniency, the Classic mod, spinners, Difficulty Adjust / Mirror / custom rates, failed plays.
  Checked on Nikita's 111 lazer replays: 300/100/50/miss exact on 109; all 13 stored statistics + max
  combo exact on 78. Slider tails are 0.1% too generous (see below). Three of his replays are test fixtures.
- **One-click lazer import**: *Improve a skill → osu!lazer → Make lazer import folder* (or
  `osu-coach playlist SKILL --lazer`) builds `Downloads/osu-coach lazer import/<playlist>/` with
  `osu!.user.cfg`, `collection.db` and `Songs/<set id>/` (missing maps, downloaded and unpacked), and opens
  it in Explorer. lazer's setup wizard → Import takes maps and collection from it in one go. The layout
  follows lazer's source (`LegacyImportManager`, `LegacyBeatmapImporter`, `LegacyCollectionImporter`).
- **Tips checked on Nikita's own data** (122 lazer + old stable replays): comfort ≈ 6.2★, UR 205, streams
  clean to ~210 BPM — so not a beginner; tips were tuned for what the data shows:
  - the aim-miss tip now says *where* the aim misses are (his: 49% in streams) and points to the matching
    playlist instead of always "Jump aim";
  - "extra presses" no longer counts aim misses (new press outcome `off_target`): pros ~0.1–0.4, Nikita
    0.9 per 100 notes; the tip threshold is now 3;
  - reading tips (AR, dense parts) compare misses with what the difficulty predicts, not raw miss rates;
  - logits in the miss model are clipped (no numpy overflow warnings).
- **Tests**: 149 pass (`.venv\Scripts\python -m pytest`). They never read the osu! installs of the computer
  they run on (`OSU_COACH_NO_AUTODETECT=1` from `tests/conftest.py`).
- **Windows**: `run.bat` checked on this PC from a clean copy (first run creates `.venv` with a real
  `python.exe`; the `py`/`python` app aliases can hang on this PC). The UI listens on localhost only. All
  pages were checked in Chrome with `dev_tools/dogfood.py` (no exceptions, no console errors).

**Nikita plays osu!lazer** (Mot1one). The project is at `C:\Users\Motion\osu-coach`.

## Next steps, in order

1. **Try the lazer import folder in the game once.** Make a playlist folder, run lazer's setup wizard →
   Import with it, check that the collection shows up with all its maps. (Not clicked through yet.)
2. **Calibrate for mid-level players.** `TYPICAL_CHAIN_RATIO` (2.0) and the skill-score scales come from
   pro replays. Nikita's consistency score (26, chain ratio 3.5×) may be normal for ~6★ players; collect
   replays of a few players around his level (`dev_tools/fetch_test_data.py`) and re-check.
3. **Speed-changing lazer mods.** Replays with Wind Up / Wind Down / Adaptive Speed are skipped (9 of
   Nikita's). Support needs a time-varying rate in the simulation and in the beatmap timing.
4. **Slider-tail timing.** lazer judges the tail at the first game update after end − 36 ms; the
   simulation uses exactly end − 36 ms, which counts ~0.1% too many tail hits. Judging ~0.5 ms later
   matches slightly better, but that is fitting to his update rate.
5. **Small clean-ups**: `levels.aim_level` / `speed_level` use a different unit than comfort stars and are
   not shown anywhere; drop or rework them.

## Layout

- `osu_coach/`: `osr`, `beatmap`, `curves`, `judge` (stable rules, dispatches lazer replays),
  `judge_lazer`, `features`, `analysis`, `difficulty`, `profile`, `advice`, `pool` (with
  `data/pool.json.gz`), `collection_db`, `lazer_import`, `locate`, `library`, `sources`, `cli`,
  `webapp/app.py`.
- `tests/`: real replays and maps in `tests/resources` (incl. three of Nikita's lazer plays,
  `mot1one__lazer_*.osr`).
- `dev_tools/`: `validate_sim`, `debug_sim`, `trace_slider`, `fetch_test_data`, `fetch_pool_raw`,
  `build_pool`, `dogfood`.
  - `dogfood` needs Playwright in a scratch venv (`pip install playwright`) and finds the system Chrome
    (or set `CHROME=`).
- `dev_data/` is not in git or in the archive. Recreate it with:
  `python dev_tools/fetch_test_data.py dev_data` and
  `python dev_tools/fetch_pool_raw.py dev_data/pool_raw 40 100`.

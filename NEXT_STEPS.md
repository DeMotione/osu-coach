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
- **Latest N replays**: the Replays page has *Replays to read: Latest 100 / 500 / 1000 / All* (default 500,
  remembered); CLI `analyze --latest N`. The scan reads replay files newest first (file time) and stops once
  the newest N plays of the main player are certain (`locate.NewestReplays`: the N-th newest play must be
  more than a day newer than the next unread file, since a replay file is written when it's played; the
  day covers time-zone mix-ups). Maps the scan didn't reach are looked up on demand, newest files first
  (`Library.find_maps`, `LazerStore.find`, `SongsFolder.find`). Replays with lazer mods the simulation
  can't follow no longer count towards N (their mods are read from the replay header). Checked on this PC:
  for N = 5…1000 the limited scan picks exactly the replays a full scan would. Files in lazer's store are
  now classified from a 64-byte probe instead of a 64 KB read (same result on all 12,105 files here).
  On this PC (146 replays, 12k store files) a first scan takes ~1 s either way; the gain is for big
  installs and for the analysis (100 replays ≈ 10 s).
- **Progress by month (SQLite)**: `progress.py` keeps `progress.sqlite` (data folder): table `replays` (one
  row per analysed replay, never deleted) and `month_metrics` (skills etc.). Every analysis in the app and
  `analyze` / `playlist` in the CLI save to it (`progress.update`, ~4 s for Nikita's 123 replays; earlier
  analyses come from the analysis cache). Progress page + `osu-coach progress`. Monthly skills use ONE
  model fitted on all of the player's replays (per-month models would hide improvement — tested), only for
  months with 5+ plays. "Hardest pass" = finished with ≤ 5 misses per 100 notes (`profile.clean_pass`;
  lazer let him finish a 9★ map at 63% with 265 misses). Nikita, Sep → Oct 2026: comfort 6.01 → 6.13★,
  UR 190 → 173, aim 48 → 68, speed 26 → 43, reading 21 → 44. Old months (2017–2021) only have the few
  replays kept from then.
- **"Where your clicks land" rechecked** (looked too perfect): the click data is right (equal to the replay
  frames, checked), but the old chart (1) rotated every jump, which cancels any constant offset — the "×"
  was at the centre by construction; (2) drew density contours that hid the outer 25% of clicks and all
  aim misses. Now: dots of a random sample of all clicks (true share of misses), *On screen* / *Along the
  jump* views, real numbers (Nikita: average 0.5 px left, 0.3 px low ± 0.1; 2.4% outside).
  `profile.click_points` / `click_summary`.
- **Setup**: tablet area X/Y (OpenTabletDriver centre) → *Tablet area to try* (`advice.suggest_tablet_area`);
  keys = keyboard / rapid-trigger keyboard / **SayoDevice** with all configurator fields →
  `advice.sayo_settings` (Now → Try + checks). Semantics from SayoDevice docs/osu! forum: Trigger/Release
  fixed depths; inside RT Upper..Lower Bound (or Full Stroke) RT Trigger/RT Release distances apply. With
  Nikita's values (Trigger 0.40, Release 0.35, RT 0.10/0.15, bounds 0.10–3.80) and tapping (2 double
  presses per 1000, 0.9 extra taps per 100 notes) the tip says they fit.
- **Tests**: 186 pass (`.venv\Scripts\python -m pytest`). They never read the osu! installs of the computer
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
6. **Progress page tuning once more months exist**: maybe a per-skill detail view, and caching the
   all-time model so `progress.update` only recomputes the months that changed (now all months, ~4 s).
7. **SayoDevice rules from real data**: the thresholds (double presses ≥ 5/1000, early releases ≥ 40% of
   slider breaks, …) are the rapid-trigger ones; check them once Nikita changes settings and replays more.
8. **Faster map lookup for big stable installs.** A *Latest N* scan hashes `.osu` files newest first until
   the replays' maps turn up; reading `osu!.db` (MD5 → file for every map) would make that instant. lazer's
   equivalent is `client.realm` (Realm format, harder).

## Layout

- `osu_coach/`: `osr`, `beatmap`, `curves`, `judge` (stable rules, dispatches lazer replays),
  `judge_lazer`, `features`, `analysis`, `difficulty`, `profile`, `advice`, `pool` (with
  `data/pool.json.gz`), `collection_db`, `lazer_import`, `locate`, `library`, `progress`, `sources`, `cli`,
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

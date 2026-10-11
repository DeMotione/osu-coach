# osu-coach: where we stopped (2026-10-10, after the review)

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
- **Replay check** (`check.py`, page *Replay check*, `osu-coach check [file]`): one replay on its own —
  misses/combo breaks with osu! editor timestamps (mm:ss:mmm), reason + detail + pattern, clusters, timing
  chart, clicks, comparison with the same map before and plays at ±0.5★ (progress.sqlite). Opens on the
  newest replay (quick scan of the newest 100 if nothing was scanned), any replay from the list, a dropped
  .osr, or *Check this replay* on a row of the Replays page. "miss" = judged miss (results screen); a slider
  head missed while the slider still scored is a "combo break"; slider breaks from the simulation. Found
  with it: Nikita's newest play (Harumachi Clover [Easy], 2026-10-10 12:42) has every click ~24 px right of
  the notes (other plays: under 1 px on average) — was the tablet area moved?
- **Tests**: 231 pass (after review round 2) (`.venv\Scripts\python -m pytest`). They never read the osu! installs of the computer
  they run on (`OSU_COACH_NO_AUTODETECT=1` from `tests/conftest.py`).
- **Windows**: `run.bat` checked on this PC from a clean copy (first run creates `.venv` with a real
  `python.exe`; the `py`/`python` app aliases can hang on this PC). The UI listens on localhost only. All
  pages were checked in Chrome with `dev_tools/dogfood.py` (no exceptions, no console errors).

## Review round (2026-10-10, owner-approved list)

- **Difficulty weighting** (`profile.replay_weight`, `detect_level`): level = comfort ★ of the replays of the last
  30 days before the newest one (≥ 15 newest); weight 1 within ±0.5★, Gaussian σ 0.5★ outside (1★ off 0.61,
  2★ 0.01, 3★ ≈ 0). Every statistic in `build_profile` is weighted (column `w` on objects / presses): miss
  causes, skills (weighted miss model too), stamina, UR, stream speed, aim regression (WLS), tapping signals
  for the setup tips, quadrant / direction / distance tables; map suggestions use the level. Overview shows
  the level, the band and *Set my level by hand* (setting `level_override`, CLI `--level`). Progress stays
  unweighted (`build_profile(..., weighted=False)`) so months compare.
- **Speed-aim miss cause** (`profile.miss_causes`): aim misses in bursts/streams (3+ notes, any spacing) and
  on jumps ≤ 125 ms apart. `aim.split` compares aim vs speed-aim with the misses the difficulty predicts.
  Stream speed is judged on finger misses only (`tap_miss_rate`); stamina only on long streams up to the
  clean stream speed + 10 BPM (`stamina_score`).
- **Fall-behind analysis** (`profile.stream_fall_behind`): hinge fit of timing vs note number → where the
  delay starts (notes, seconds at the typical BPM). Nikita: no clear onset — he rushes late in streams.
- **Selection** (`selection.py`): date windows (last session = < 1 h between plays, 7 / 30 days, custom),
  *Only these files* mode, *All / Best replays* (passed plays, best per beatmap + speed by score then
  accuracy; setting `replay_set`, CLI `--best` / `--all-replays`, both remembered).
- **UI**: renamed pages (Sliders & Reading, Tips & Setup, Map Suggestion, Skill Development), a subtext under
  every title, no header link icons, Difficulty / Detail description columns, bulk download on Map Suggestion,
  aim calibration box + tip on Tips & Setup. **Light/dark**: `osu-coach ui` passed `--theme.base dark` + fixed
  colours, which removes System/Light/Dark from Streamlit's menu (checked); now only the accent is set per
  theme and charts have no fixed plotly template.
- Nikita, all 123 replays: level 6.08★; misses aim 38% / speed-aim 27% / lost 21% / no tap 11% (was aim 66%);
  stream comfort 230 BPM (was 210: DT/spaced-stream aim misses counted as tapping); stamina 32 (on 3,696 notes
  of reachable streams instead of 5,899). Last 7 days: stream comfort 210 (180 before) — that week has no
  faster streams to measure, so his 240–250 can't be confirmed from the data yet.
- `dev_tools/profile_numbers.py` prints these numbers (all / best, all time / 7 days) for before/after checks.

**Nikita plays osu!lazer** (Mot1one). The project is at `C:\Users\Motion\osu-coach`.

## Review round 2 (2026-10-10, ilikegirls' review v2)

- **Tapping**: *Hit timing* bars stacked by 300 / 100 / 50 (+ log-scale toggle). *Stream speed* UR is now the
  median of per-play URs per 10 BPM (`profile._play_urs`; `ur_pooled` keeps the old pooled number, which mixed
  the offsets of different plays: two 100 UR plays 20 ms apart pool to ~141), `ur_best` = best play, a rising
  weighted trend line refitted without outliers (`ur_trend`), bins ≥ 15% and ≥ 15 UR above it = `weak`.
- **Stamina in long streams** (`stream_fall_behind`, rewritten): mean ABSOLUTE error by note number in streams of
  16+ notes up to clean speed + 10 BPM, one chart line per length group (16–31 / 32–63 / 64+, 4-note bins),
  hinge fit → `start_note` (needs ≥ 0.1 ms/note, ≥ 3 ms and ≥ 20% growth), `comfort_notes`, `practice_notes`;
  map suggestions by longest stream (`pool.stream_length_maps`).
- **Stamina skill v3** (`stamina_score`, `stream_loads`, `stream_rhythm`, on Xo's request): load = notes ×
  (BPM/200)³ × quality; quality = kept part (≥ 90% pressed = 1, ≤ 60% = 0, linear) × steady (key presses of
  16+ streams, 2-tap gaps, 2nd vs 1st half: > 3% slower costs 2.5×, rhythm spread growth > 0.05 costs 1×,
  floor 0.3; still tapping ≥ 5% faster than the notes at the end = overstreaming = no cost). Three parts, top-5
  each: streams 16+ (ref 32 notes), most load in any 30 s of a play (ref 140), finished-map total (ref 400);
  refs at `stamina_ref_bpm(level)`; +25 per doubling; score = mean. `_skills` / `progress` pass the presses.
  Nikita (123 replays): 74.6 (streams 71.5, 30 s 70.7, maps 81.5), steadiness 95%, 61 of 276 long streams
  slowed down, 22 overstreamed. Was 76.6 with v2. The refs are still a first guess.
- **Detailed Map Analysis** (renamed from Replay check): second metric row (BPM, UR, speed, AR/OD/CS/HP, length);
  `check.map_plays` / `compare` list every play of the map (progress.sqlite + replay files on the computer, up to
  50 analysed) and judge best only within the same `settings_key` (rate, CS/AR/OD/HP, HD/FL); the ±0.5★
  comparison is gone. `check.practice_sections`: clusters widened by a measure before / half after, on whole
  notes, with seconds and note count. progress.sqlite schema 2 adds `hp` and `path` (migrated on connect).
- **UI**: no click-and-drag zoom anywhere (`app.plot`), the sidebar collapse button always visible (CSS on
  `stSidebarCollapseButton`; not checked in a real browser this round).

## Calibration round (2026-10-11, 38 reference replays)

ilikegirls downloaded 38 of the 39 plays in `dev_tools/reference_replays.md` (Assailant in The Night: Merami's
score is gone). Replacements, same maps: milosz Mou Ii kai? HDDT 97.57%; Ivaxa both Stream Practice Maps HDDT
(97.94% / 98.08%); chocomint A Sacred Lot HDDT 99.49%; MALISZEWSKI KARMANATIONS HDHR SS. Different plays of the
listed player: aetrna Ascension HDDTHR 96.40%, JGLF Isolation 99.93%, MALISZEWSKI AKAGE HDHR; plambob = "Plasma".
Files in `reference_replays/` (ignored by git); `dev_tools/reference_analysis.py` gives the group numbers below.

- **Pattern detection is right**: jump maps have the most jumps (216–973), AR0 maps the highest density (p90 11–22
  vs 3–9), stream maps the most stream notes. Flow aim (`spaced_stream`: 3+ notes ≥ 0.9 diameters) also fires a
  lot on jump maps (Sound Chimera 49%, LONG SEASON 55%) — consider a stricter spacing / snap rule.
- **Accuracy**: single-note 300 share of all 38: 0.82–1.00, median 0.98; the old scale (100 at 95%) put almost all
  at 100. Now `ACCURACY_TOP` = 0.99 (groups 86.6–99.0).
- **Miss-model skills** (aim, flow aim, speed, reading) and **consistency**: 0–4 misses per group, so no score —
  by design they're relative to the player's own miss model. They now report `too_few_misses`. Pros can't set
  their 50; that still needs mid-level replays (next step 2).
- **Sliders**: 37 of 38 plays have 0 breaks → 100. Nothing to move.
- **Stamina (open)**: stream specialists 84–100 (ENTANGLE NIGHT 100, rog-limitation 100, Snow Goose 93,
  NE PLACH' 86), tapping 63–100, flow 57–87, but **Kingling's 53-min The Unforgiving HDHR scores 0** and the
  30-min marathons 24–27: only streams of 8+ notes load, at (BPM/200)³, so long maps of slower 1/2 notes count for
  nothing. **Done (ilikegirls' choice)**: endurance part (`endurance_loads`, `endurance_ramp`): kept notes of
  finished plays × linear speed × ramp (×1 < 5 min, +1 per doubling: ×2 from 5, ×3 from 10, …), 5 s gaps pause
  the clock; top-5 plays vs `ENDURANCE_REF` × ref_bpm/200; final = max(S, min(S + ½·(E − S), 80)) with S = the
  old stream-based score, so marathons only lift it and never above 80 alone. Reference: The Unforgiving 0 → 50,
  LONG SEASON 24 → 62, marathon group 37 → 68 (stream group 84, unchanged).

## Stamina and sliders rebuilt (2026-10-11, owner's request)

- **Stamina** = tempo you keep up × for how long (`tempo_curve`, `stamina_score`): best kept tempo for 10 s / 30 s /
  1 / 2 / 5 min (kept share ≥ 90% = full, ≤ 60% = 0), best 3 maps each, vs `stamina_ref_bpm` × `STAMINA_WINDOW_SHARE`,
  75 points per doubling, averaged. Replaces the stream-load parts and the endurance part (removed). Stream
  steadiness stays as information. Owner (6.08★): 75 → 62 (10 s 184, 30 s 162, 1 min 150, 2 min 135, 5 min 94).
  Reference groups: stamina 60 (ENTANGLE NIGHT 272 / 270 / 259 / 216 BPM), the marathon The Unforgiving stays low
  (100 / 77 / 60 / 48 / 43), so marathons can't beat controlled death streams.
- **Sliders** = how hard the sliders are you hold (`slider_difficulty`, `slider_score`; new object columns
  `slider_turn`, `slider_corners`, `slider_bends`, `slider_vel_change`, `slider_next_gap`; `ANALYSIS_VERSION` 7).
  Owner 99 → 87; slider group 63 (AKAGE / Magic people / Euclid high, Burning Star has almost no hard sliders, so
  it is a poor reference pick). Shares and weights are first guesses: check them on more players.

## Next steps, in order

0. **Check the weighting and speed-aim split against how Nikita feels he plays** after a week of new replays:
   if 240–250 BPM streams show up, stream comfort should follow; tune `LEVEL_SIGMA` / `FAST_JUMP_MS` if the
   split looks off. Consider a per-skill level (aim vs speed) for the weighting.

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

- `osu_coach/`: `osr`, `beatmap`, `curves`, `judge` (stable rules, dispatches lazer replays), `check`,
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

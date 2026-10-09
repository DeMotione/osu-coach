# osu-coach: where we stopped (2026-10-09)

## Current state

All planned features are built: replay and beatmap parsing, judgement re-simulation, statistics, skill
scores, quadrant analysis, tips, map pool, skill playlists, collection export, osu! auto-discovery, CLI
and Streamlit UI.

- 128 tests pass (`.venv/bin/python -m pytest`).
- All UI pages were checked in real Chrome (`dev_tools/dogfood.py`).
- To start: `./run.sh` or `run.bat`, or `osu-coach ui` / `osu-coach analyze --folder DIR`.

**Nikita plays osu!lazer.**

## Next steps, in order

1. **Run it on Nikita's own lazer replays.**
   - Where to find them: lazer's data folder (`%APPDATA%\osu`). Replays are found inside `files/`
     automatically. Replays exported from the results screen land in `exports/`.
   - Check that the levels and tips make sense for a beginner, and tune the thresholds:
     `advice.py`, `profile._skills`, `TYPICAL_CHAIN_RATIO` (currently calibrated on pro replays).
2. **Make lazer judgement accurate.**
   - Today lazer replays use stable rules plus lazer's hit policy (`judge.simulate(rules="lazer")`).
   - Port lazer's slider judgement (head/tick/tail scoring), its unrounded hit windows, and the
     behaviour of the Classic mod.
   - Validate against the statistics stored in lazer replays (`replay.lazer["statistics"]`:
     great/ok/meh/miss, large_tick_hit, slider_tail_hit).
3. **Make lazer collection import easy.**
   - Lazer only imports from a folder that looks like a stable install, so it needs an `osu!.*.cfg`
     file next to `collection.db`. The UI and CLI texts now say so.
   - Better: offer a one-click "lazer import pack" zip containing `collection.db` and an empty
     `osu!.user.cfg`.
4. **Smaller fixes.**
   - The "extra presses" metric looks high on pro replays (about 5 per 100 notes): check the judge's
     press outcomes.
   - Clip the logits in `profile.fit_miss_model` to stop numpy overflow warnings.

## Layout

- `osu_coach/`: `osr`, `beatmap`, `curves`, `judge`, `features`, `analysis`, `difficulty`, `profile`,
  `advice`, `pool` (with `data/pool.json.gz`), `collection_db`, `locate`, `library`, `sources`, `cli`,
  `webapp/app.py`.
- `tests/`: real replays and maps are in `tests/resources`.
- `dev_tools/`: `validate_sim`, `debug_sim`, `trace_slider`, `fetch_test_data`, `fetch_pool_raw`,
  `build_pool`, `dogfood`.
  - `dogfood` needs Playwright in a scratch venv plus the system Chrome.
- `dev_data/` is not in git or in the archive. Recreate it with:
  `python dev_tools/fetch_test_data.py dev_data` and
  `python dev_tools/fetch_pool_raw.py dev_data/pool_raw 40 100`.

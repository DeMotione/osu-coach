# rosu-pp-2026

Prebuilt wheels of **rosu-pp-2026**: rosu-pp-py 4.0.2's Python bindings, built on rosu-pp's port of osu!'s
[star rating and pp update of 2026-07-03](https://osu.ppy.sh/home/news/2026-07-03-performance-points-star-rating-updates).
osu! coach takes every star rating, skill rating and pp from it, so its stars are the ones osu! shows (#128).

The port is in rosu-pp's `pp-update` branch, which isn't released yet
([rosu-pp#76](https://github.com/MaxOhn/rosu-pp/issues/76)), so it isn't on PyPI. These wheels pin the branch at
`072ed25`. On 158 pool maps, they matched osu!'s star ratings to within 0.0005★. rosu-pp-py 4.0.2 from PyPI implements
osu!'s 2025 model; it matched only 12 of those maps to within 0.01★ and was off by up to 0.5★.

## How it's used

- `constraints.txt` points pip here (`--find-links vendor/rosu-pp-2026`) and pins the version. Every install that
  uses it (`pip install -c constraints.txt ...`, CI, the release builds) finds the wheel with no extra step.
- The module is `rosu_pp_2026`, not `rosu_pp_py`, so it installs beside rosu-pp-py 4.0.2 from PyPI. The app still
  reads per-note strain peaks from rosu-pp-py. The 2026 model keeps only aim's hardest sections, in no order, and
  speed per note, so it can't show where in a map the hard parts are. See `infra/beatmaps/difficulty.py` and
  decision 30 in `docs/star-scale-irt.md`.
- Wheels: Windows and Linux (manylinux2014), x86_64, CPython 3.11 to 3.14. There are none for macOS or ARM.

## Rebuilding

`build.sh` (Windows, Git Bash; it needs git, uv and Rust with the GNU toolchain) rebuilds every wheel into this
folder:

1. It clones rosu-pp-py v4.0.2 into a temporary folder.
2. `patch_binding.py` pins rosu-pp to the branch, sets the version and exposes osu!'s new reading skill (`reading`,
   `reading_difficult_note_count`, `pp_reading` and reading strains).
3. It renames the module to `rosu_pp_2026`.
4. maturin builds the wheels. The Linux wheels are cross-compiled with zig.

To move to a newer commit of the branch, change `ROSU_PP_REV` in `patch_binding.py`, run `build.sh`, update the pin
in `constraints.txt`, and rebuild the data that holds its numbers. "Rebuilding the data" below gives the order.

## When rosu-pp-py releases the 2026 update

Switch to it and delete this folder:

1. Replace `rosu_pp_2026` with `rosu_pp_py` in `infra/beatmaps/difficulty.py` and `performance.py`.
2. Drop the `rosu-pp-2026` lines from `backend/pyproject.toml`, `constraints.txt`, `packaging/osu-coach.spec` and the
   import-linter contract.
3. The per-note strains then need porting to the new model (see above), or a second, renamed copy of rosu-pp-py 4.
4. Rebuild the data.

## Rebuilding the data

After any change of calculator, rebuild these in order:

1. `backend/tools/build_pool.py RAW_DIR`
2. `build_irt_tables.py`
3. `fit_demand_curves.py`
4. `build_goal_pool.py RAW_DIR/osu`
5. `build_variant_table.py RAW_DIR`: move `RAW_DIR/variants/` aside first, because its finished blocks are kept by
   map, not by calculator.

Then bump `ANALYSIS_VERSION`.

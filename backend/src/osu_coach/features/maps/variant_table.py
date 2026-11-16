"""The pool's mod and rate configurations, calculated once for every map and read without any .osu file.

A search with mods ranks up to 368 configurations of every pool map (Hard Rock x Hidden x 92 rates). Calculating
them from the map files takes hours on a pool of 50,000 maps, and needs every file. This table holds what a
configuration's row is made of instead (``tools/build_variants.py`` makes it from the map files):

- what osu!'s difficulty calculation gives for each configuration: stars, aim, speed, slider factor, max combo, and
  the evenness of the map's sections (the same with and without Hidden);
- the pattern statistics of each map at rate 1, without and with Hard Rock. At another rate each of them is the
  same, times the rate (tempos, speeds) or divided by it (durations), and AR / OD follow from their formulas;
- for the few maps where that isn't so (slow maps, whose notes join into streams when sped up, and gaps the 25 ms
  velocity limit applies to), the statistics that differ, at every rate.

Values are kept to the pool file's precision (4 decimals; aim, speed and evenness 3). :func:`VariantTable.results`
gives the rows a search ranks, like ``variant_repository.variant_rows`` does from the files.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import zipfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path

import numpy as np

from osu_coach.domain.beatmaps.features import RUN_DT_MAX, RUN_SNAP_MAX, features_at_rate, object_features
from osu_coach.domain.beatmaps.models import PlayableBeatmap
from osu_coach.domain.maps.configuration import SearchOptions
from osu_coach.domain.maps.skillset import STAR_WINDOW, Screened
from osu_coach.domain.maps.suggestions import pattern_stats
from osu_coach.domain.player.algorithm import MODEL_VERSION
from osu_coach.domain.replays.configuration import Configuration
from osu_coach.infra.beatmaps import difficulty
from osu_coach.infra.beatmaps.parser import parse_beatmap_bytes
from osu_coach.infra.beatmaps.performance import CALCULATOR_VERSION
from osu_coach.infra.map_pool import POOL_PATH
from osu_coach.infra.map_stats import evenness

TABLE_VERSION = 1
TABLE_PATH = POOL_PATH.with_name("pool_variants.zip")
CHUNK = 500  # maps to a part of the file: read, ranked and dropped one after another

# every configuration a search can ask for, in blocks of the rates: no mod, HD, HR, HD + HR
GRID = SearchOptions(allow_hr=True, allow_hd=True, adjustable_dt=True)
_CONFIGS = GRID.configurations("")
BLOCKS = 4
RATES = len(_CONFIGS) // BLOCKS
RATE = np.array([c.rate for c in _CONFIGS[:RATES]])
RATE_HUNDREDTHS = np.rint(RATE * 100).astype(int)
MAX_RATE = float(RATE.max())
_DT_STARS = int(np.nonzero(RATE_HUNDREDTHS == 150)[0][0])  # stars_dt of a no-mod row: its stars with Double Time
# a block's mods as the rows name them, without and with a rate
_MODS = (("NM", "DT"), ("HD", "HDDT"), ("HR", "HRDT"), ("HDHR", "HDHRDT"))

# the numbers pattern_stats gives, in the order they are kept
PATTERN = (
    "cs", "ar", "od", "hp", "hit300_ms", "hit100_ms", "hit50_ms", "bpm", "drain_length", "n_objects",
    "circle_share", "slider_share", "stream_share", "burst_share", "jump_share", "spaced_share",
    "spaced_stream_share", "stream_bpm", "burst_bpm", "speed_bpm", "speed_runs", "max_run", "run_duration_p90",
    "run_rest_median", "long_runs", "stream_notes", "n_jumps", "jump_dist", "jump_velocity", "flow_velocity",
    "flow_turn_share", "sharp_share", "slider_velocity", "slider_length_norm", "slider_turn", "slider_transition",
    "reverse_share", "density_p90", "density_median", "odd_rhythm_share",
    "q_top_left", "q_top_right", "q_bottom_left", "q_bottom_right",
)  # fmt: skip
_TEXT = ("md5", "title", "artist", "version", "creator", "beatmap_id", "beatmapset_id")
_COL = {name: i for i, name in enumerate(PATTERN)}
_UP = [_COL[k] for k in ("bpm", "stream_bpm", "burst_bpm", "speed_bpm", "jump_velocity", "flow_velocity", "slider_velocity")]  # fmt: skip
_DOWN = [_COL[k] for k in ("hit300_ms", "hit100_ms", "hit50_ms", "drain_length", "run_duration_p90", "run_rest_median", "slider_transition")]  # fmt: skip
_WHOLE = [_COL[k] for k in ("n_objects", "speed_runs", "max_run", "long_runs", "stream_notes", "n_jumps")]
_NAN = np.iinfo(np.int64).min
# an exact statistic this far from the one worked out from rate 1 (kept to 4 decimals) is kept on its own
_TOLERANCE = 2e-4


def at_rate(base: np.ndarray, rate: np.ndarray) -> np.ndarray:
    """The pattern statistics (rows of ``PATTERN``) of maps at ``rate``, from the ones at rate 1."""
    out = np.array(base, dtype=float)
    rate = np.asarray(rate, dtype=float)[..., None]
    out[..., _UP] *= rate
    out[..., _DOWN] /= rate
    # AR and OD from the whole milliseconds they stand for (PlayableBeatmap.effective_ar / effective_od)
    ar = np.asarray(base, dtype=float)[..., _COL["ar"]]
    preempt = np.rint(np.where(ar >= 5, 1200 - (ar - 5) * 150, 1200 + (5 - ar) * 120)) / rate[..., 0]
    out[..., _COL["ar"]] = np.where(preempt < 1200, 5 + (1200 - preempt) / 150, 5 - (preempt - 1200) / 120)
    hit300 = np.rint(np.asarray(base, dtype=float)[..., _COL["hit300_ms"]] + 0.5)
    out[..., _COL["od"]] = (79.5 - (hit300 - 0.5) / rate[..., 0]) / 6
    return out


def _quantise(values, decimals: int, missing: int = -1) -> np.ndarray:
    v = np.asarray(values, dtype=float)
    return np.where(np.isnan(v), missing, np.rint(np.nan_to_num(v) * 10**decimals)).astype(np.int64)


def _real(values: np.ndarray, decimals: int, missing: int = -1) -> np.ndarray:
    return np.where(values == missing, np.nan, values / 10**decimals)


# ------------------------------------------------------------------ making the table
def _follows_the_rate(template) -> bool:
    """Whether the map's statistics at every rate of the grid follow from the ones at rate 1: no note becomes part
    of a run when sped up (``_label_runs``), and no gap a velocity is taken over gets under the 25 ms limit."""
    notes = template.kind != "spinner"
    joins = (
        notes & (template.snap <= RUN_SNAP_MAX) & (template.dt > RUN_DT_MAX) & (template.dt <= RUN_DT_MAX * MAX_RATE)
    )
    used = notes & (np.isin(template.pattern.astype(str), ("jump", "spaced")) | template.spaced_stream)
    return not joins.any() and not (used & (template.dt_end < 25.0 * MAX_RATE)).any()


def _numbers(stats: Mapping) -> list[float]:
    extra = set(stats) - set(PATTERN) - set(_TEXT)
    if extra or set(PATTERN) - set(stats):
        raise RuntimeError(f"pattern_stats changed: update variant_table.PATTERN ({sorted(extra)})")
    return [math.nan if stats[k] is None else float(stats[k]) for k in PATTERN]


def build_map(raw: bytes, check_every_rate: bool = False) -> dict[str, np.ndarray]:
    """One map's entry of the table. ``check_every_rate``: compare the statistics at every rate with the exact ones
    also when they should follow from rate 1 (to test that rule; many times slower)."""
    entry = {
        "stars": np.zeros((BLOCKS, RATES), np.int64),  # 0: no statistics, -1: stars unknown
        "aim": np.full((BLOCKS, RATES), -1, np.int64),
        "speed": np.full((BLOCKS, RATES), -1, np.int64),
        "slider": np.full((BLOCKS, RATES), -1, np.int64),
        "combo": np.full((BLOCKS, RATES), -1, np.int64),
        "even": np.full((2, RATES), -1, np.int64),
        "base": np.full((2, len(PATTERN)), _NAN, np.int64),
        "differs": np.zeros((0, 2), np.int64),  # (0 / 1: with Hard Rock, column of PATTERN)
        "differs_values": np.zeros((0, RATES), np.int64),
        "same": np.ones(2, bool),  # lazer's calculation gives the same; Hidden leaves the evenness as it is
    }
    try:
        bm = parse_beatmap_bytes(raw)
    except Exception:  # noqa: BLE001 - a broken file has no statistics
        return entry
    parsed = difficulty.parse_map(raw) if bm.mode == 0 and len(bm.objects) >= 30 else None
    if parsed is None or not any(o.kind != "spinner" for o in bm.objects):
        return entry
    configs = GRID.configurations(hashlib.md5(raw).hexdigest())
    differs: list[tuple[int, int]] = []
    values: list[np.ndarray] = []
    usable = [False, False]
    for hr in (0, 1):
        block = configs[hr * 2 * RATES : (hr * 2 + 1) * RATES]
        template = object_features(PlayableBeatmap(bm, block[0].mods, rate=1.0))
        first = pattern_stats(bm, raw, block[0].mods, 1.0, template)
        if first is None:
            continue
        usable[hr] = True
        entry["base"][hr] = _quantise(_numbers(first), 4, _NAN)
        if not check_every_rate and _follows_the_rate(template):
            continue
        exact = np.array(
            [_numbers(first)]
            + [_numbers(pattern_stats(bm, raw, c.mods, c.rate, features_at_rate(template, c.rate))) for c in block[1:]]
        )
        worked_out = at_rate(np.broadcast_to(_real(entry["base"][hr], 4, _NAN), exact.shape), RATE)
        off = ~np.isclose(exact, worked_out, rtol=1e-9, atol=_TOLERANCE, equal_nan=True)
        for column in np.nonzero(off.any(axis=0))[0]:
            differs.append((hr, int(column)))
            values.append(_quantise(exact[:, column], 4, _NAN))
    if differs:
        entry["differs"] = np.array(differs, np.int64)
        entry["differs_values"] = np.array(values, np.int64)
    probe = RATES // 2
    for index, config in enumerate(configs):
        block, rate = divmod(index, RATES)
        hr = block // 2
        if not usable[hr]:
            continue
        a = difficulty.attributes(raw, config.mods, rate=config.rate, parsed_map=parsed)
        stars = a.get("stars", math.nan)
        entry["stars"][block, rate] = _quantise(stars, 4)
        if not stars:  # 0 or unknown: nothing else is read
            continue
        entry["aim"][block, rate] = _quantise(a.get("aim", math.nan), 3)
        entry["speed"][block, rate] = _quantise(a.get("speed", math.nan), 3)
        entry["slider"][block, rate] = _quantise(a.get("slider_factor", 1.0), 4)
        entry["combo"][block, rate] = _quantise(a.get("max_combo", math.nan), 0)
        if not config.hd:
            entry["even"][hr, rate] = _quantise(evenness(raw, config.mods, config.rate, parsed_map=parsed), 3)
        if rate == probe:
            if difficulty.attributes(raw, config.mods, rate=config.rate, lazer=True, parsed_map=parsed) != a:
                entry["same"][0] = False
            if (
                config.hd
                and _quantise(evenness(raw, config.mods, config.rate, parsed_map=parsed), 3) != entry["even"][hr, rate]
            ):
                entry["same"][1] = False
    return entry


def build_file(path: str, md5: str, check_every_rate: bool = False) -> dict[str, np.ndarray] | None:
    """The entry of the map in ``path`` (None: not there, or not the pool's version of the map)."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None
    return build_map(raw, check_every_rate) if hashlib.md5(raw).hexdigest() == md5 else None


_PER_CONFIG = ("stars", "aim", "speed", "slider", "combo")


def pack_chunk(md5s: Sequence[str], entries: Sequence[dict[str, np.ndarray] | None]) -> bytes:
    """A part of the file: the entries of ``md5s`` (None: no map file), as differences that compress well (a Hidden
    block against the one without, then each rate against the one before)."""
    empty = build_map(b"")
    given = [e if e is not None else empty for e in entries]
    arrays: dict[str, np.ndarray] = {
        "md5": np.frombuffer(bytes.fromhex("".join(md5s)), np.uint8).reshape(len(md5s), 16),
        "present": np.array([e is not None for e in entries]),
        "same": np.array([e["same"] for e in given]),
        "base": np.array([e["base"] for e in given]),
    }
    for name in _PER_CONFIG:
        a = np.array([e[name] for e in given])
        a[:, 1::2] -= a[:, 0::2]
        arrays[name] = np.diff(a, axis=-1, prepend=0).astype(np.int32)
    arrays["even"] = np.diff(np.array([e["even"] for e in given]), axis=-1, prepend=0).astype(np.int32)
    where = [(i, *pair) for i, e in enumerate(given) for pair in e["differs"].tolist()]
    arrays["differs"] = np.array(where, np.int64).reshape(len(where), 3)
    arrays["differs_values"] = np.concatenate([e["differs_values"] for e in given])
    out = io.BytesIO()
    np.savez(out, **arrays)
    return out.getvalue()


def _unpack_chunk(data: bytes) -> dict[str, np.ndarray]:
    with np.load(io.BytesIO(data)) as z:
        arrays = {name: z[name] for name in z.files}
    for name in _PER_CONFIG:
        a = np.cumsum(arrays[name], axis=-1, dtype=np.int64)
        a[:, 1::2] += a[:, 0::2]
        arrays[name] = a
    arrays["even"] = np.cumsum(arrays["even"], axis=-1, dtype=np.int64)
    arrays["md5"] = np.array([row.tobytes().hex() for row in arrays["md5"]])
    return arrays


def versions() -> dict:
    return {
        "table": TABLE_VERSION,
        "model": MODEL_VERSION,
        "calculator": CALCULATOR_VERSION,
        "rates": RATE_HUNDREDTHS.tolist(),
    }


def asset_name() -> str:
    """The table's file name where it is published: one per pool and version of the calculations, so a build takes
    the table made for its code and never another one."""
    pool = hashlib.sha256(POOL_PATH.read_bytes()).hexdigest()[:12]
    return f"pool_variants-t{TABLE_VERSION}-m{MODEL_VERSION}-rosu{CALCULATOR_VERSION}-{pool}.zip"


def write_table(path: Path, chunks: Sequence[bytes], maps: int) -> None:
    temp = path.with_suffix(".tmp")
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_LZMA) as z:
        z.writestr("meta.json", json.dumps({**versions(), "maps": maps, "chunks": len(chunks)}))
        for index, chunk in enumerate(chunks):
            z.writestr(f"chunks/{index:05d}.npz", chunk)
    temp.replace(path)


# ------------------------------------------------------------------ reading it
MapResult = tuple[
    int, bool, list, int, int
]  # pool index, map known, rows and Screened, configurations without statistics, asked


class VariantTable:
    """The table in ``path``, read a part at a time."""

    def __init__(self, path: Path):
        self.path = path
        with zipfile.ZipFile(path) as z:
            self.meta = json.loads(z.read("meta.json"))

    @property
    def current(self) -> bool:
        """Made by this version of the calculations (else a search has to work from the map files)."""
        return {k: self.meta.get(k) for k in versions()} == versions()

    def results(
        self,
        records: Sequence[Mapping],
        options: SearchOptions,
        client: str,
        targets: tuple[float, ...],
        played: frozenset[str] = frozenset(),
        report: Callable[[int, int, str], None] | None = None,
    ) -> Iterator[MapResult]:
        """What ``variant_repository`` gives for every pool map of ``records``, from the table: the rows of the
        configurations inside a goal's star window (``targets``), and the others counted in a :class:`Screened`.
        Maps in ``played`` are only counted (no goal ranks them). A map the table doesn't have, or one lazer
        calculates differently when ``client`` is lazer, comes as not known."""
        index_of = {str(r["md5"]): i for i, r in enumerate(records)}
        seen: set[int] = set()
        blocks = [b for b in range(BLOCKS) if (options.allow_hr or b < 2) and (options.allow_hd or b % 2 == 0)]
        low, high = round(options.min_rate * 100), round(options.max_rate * 100)
        rates = np.nonzero(
            (RATE_HUNDREDTHS == 100) | (options.adjustable_dt & (RATE_HUNDREDTHS >= low) & (RATE_HUNDREDTHS <= high))
        )[0]
        asked = len(blocks) * len(rates)
        keys = _key_templates(blocks, rates, client)
        total, done = len(records), 0
        with zipfile.ZipFile(self.path) as z:
            for number in range(self.meta["chunks"]):
                if report is not None:
                    report(done, total, f"Checking map {min(done + 1, total)} of {total}")
                chunk = _unpack_chunk(z.read(f"chunks/{number:05d}.npz"))
                for md5, result in _chunk_results(chunk, blocks, rates, keys, client, targets, played, asked):
                    index = index_of.get(md5)
                    if index is None or index in seen:
                        continue
                    seen.add(index)
                    done += 1
                    known, rows, failed = result
                    for row in rows:
                        if isinstance(row, dict):
                            record = records[index]
                            row.update({k: record.get(k) for k in _TEXT})
                    yield index, known, rows, failed, asked
        for index in range(total):
            if index not in seen:
                yield index, False, [], 0, asked
        if report is not None:
            report(total, total, "Ranking complete")


_MD5 = "0" * 32


def _key_templates(blocks: Sequence[int], rates: np.ndarray, client: str) -> list[list[str]]:
    """``Configuration.key`` of every configuration asked for, for a map whose md5 is put in afterwards."""
    return [
        [Configuration(_MD5, _CONFIGS[b * RATES + r].mods, float(RATE[r]), client).key for r in rates] for b in blocks
    ]


def _chunk_results(chunk, blocks, rates, keys, client, targets, played, asked):
    md5s = chunk["md5"]
    n = len(md5s)
    known = chunk["present"] & (chunk["same"][:, 0] | (client != "lazer"))
    pick = np.ix_(range(n), blocks, rates)
    stars_q = chunk["stars"][pick]
    stars = stars_q / 1e4
    valid = stars_q > 0
    window = np.zeros(stars.shape, bool)
    for target in targets:
        window |= np.abs(stars - target) <= STAR_WINDOW + 1e-12
    is_played = np.array([m in played for m in md5s])
    window &= valid & known[:, None, None] & ~is_played[:, None, None]
    no_stars = (stars_q < 0).sum(axis=(1, 2))
    outside = (valid & ~window).sum(axis=(1, 2))
    failed = (stars_q == 0).sum(axis=(1, 2))
    rows = _rows(chunk, np.nonzero(window), blocks, rates, keys)
    start = 0
    counts = window.sum(axis=(1, 2))
    for i in range(n):
        md5 = str(md5s[i])
        if not known[i]:
            yield md5, (False, [], 0)
            continue
        mine: list = rows[start : start + counts[i]]
        start += counts[i]
        if outside[i] or no_stars[i]:
            mine.append(Screened(md5, int(outside[i]), int(no_stars[i])))
        yield md5, (True, mine, int(failed[i]))


def _rows(chunk, where, blocks, rates, keys) -> list[dict]:
    """The rows of the configurations at ``where`` (map of the chunk, block asked for, rate asked for)."""
    m, bi, ri = where
    if not len(m):
        return []
    block = np.asarray(blocks)[bi]
    rate_index = rates[ri]
    hr = block // 2
    rate = RATE[rate_index]
    pattern = at_rate(_real(chunk["base"][m, hr], 4, _NAN), rate)
    if len(chunk["differs"]):
        kept = {(int(i), int(g)): [] for i, g, _ in chunk["differs"]}
        for k, (i, g, column) in enumerate(chunk["differs"].tolist()):
            kept[i, g].append((column, k))
        for row, pair in enumerate(zip(m.tolist(), hr.tolist(), strict=True)):
            for column, k in kept.get(pair, ()):
                pattern[row, column] = _real(chunk["differs_values"][k, rate_index[row]], 4, _NAN)
    config = (m, block, rate_index)
    numbers = {
        "stars": chunk["stars"][config] / 1e4,
        "aim": _real(chunk["aim"][config], 3),
        "speed": _real(chunk["speed"][config], 3),
        "slider_factor": _real(chunk["slider"][config], 4),
        "max_combo": _real(chunk["combo"][config], 0),
        "evenness": _real(chunk["even"][m, hr, rate_index], 3),
    }
    columns = {**{name: pattern[:, i] for i, name in enumerate(PATTERN)}, **numbers}
    columns.update(_skill_scores(columns))
    # as the rows read from a map's file: nothing for a statistic the map doesn't have, whole numbers whole
    table = np.column_stack(list(columns.values())).astype(object)
    table[np.isnan(np.column_stack(list(columns.values())))] = None
    names = tuple(columns)
    stars_dt = chunk["stars"][m, 0, _DT_STARS] / 1e4
    md5s = chunk["md5"]
    rows = []
    for k, cells in enumerate(table.tolist()):
        row = dict(zip(names, cells, strict=True))
        if block[k] == 0 and rate_index[k] == 0:
            row["stars_dt"] = float(stars_dt[k])
        for name in _WHOLE_NAMES:
            if row[name] is not None:
                row[name] = int(row[name])
        md5 = str(md5s[m[k]])
        row["md5"] = md5
        row["configuration_id"] = keys[bi[k]][ri[k]].replace(_MD5, md5, 1)
        row["mods"] = _MODS[block[k]][int(rate_index[k] > 0)]
        row["rate"] = float(rate[k])
        rows.append(row)
    return rows


_WHOLE_NAMES = tuple(PATTERN[i] for i in _WHOLE)


def _skill_scores(s: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    """``suggestions.skill_scores`` for many rows at once (a test holds the two together)."""

    def c(v, lo: float, hi: float) -> np.ndarray:
        return np.where(np.isnan(v), 0.0, np.clip((v - lo) / (hi - lo), 0.0, 1.0))

    def or_else(v, default: float) -> np.ndarray:
        return np.where(np.isfinite(v), v, default)

    aim, speed = or_else(s["aim"], 0.0), or_else(s["speed"], 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        aim_ratio = np.where(aim + speed > 0, aim / (aim + speed), 0.5)
    jumpy = or_else(s["jump_share"], 0) + 0.5 * or_else(s["spaced_share"], 0)
    tappy = or_else(s["stream_share"], 0) + 0.6 * or_else(s["burst_share"], 0)
    return {
        "s_aim": 0.6 * c(jumpy, 0.05, 0.40) + 0.4 * c(aim_ratio, 0.45, 0.60),
        "s_flow_aim": c(s["spaced_stream_share"], 0.02, 0.20),
        "s_speed": 0.7 * c(tappy, 0.05, 0.40) + 0.3 * c(1 - aim_ratio, 0.40, 0.55),
        "s_stamina": 0.5 * c(s["stream_notes"], 50, 400)
        + 0.3 * c(s["max_run"], 12, 48)
        + 0.2 * c(s["drain_length"], 90, 300),
        "s_accuracy": 0.5 * c(s["od"], 6.5, 9.5)
        + 0.3 * c(s["circle_share"], 0.3, 0.8)
        + 0.2 * (1 - c(jumpy, 0.1, 0.5)),
        "s_sliders": 0.45 * c(s["slider_share"], 0.25, 0.65)
        + 0.35 * c(1 - or_else(s["slider_factor"], 1.0), 0, 0.08)
        + 0.2 * c(s["reverse_share"], 0.05, 0.35),
        "s_reading": 0.6 * c(s["density_p90"], 4, 10) + 0.4 * c(s["odd_rhythm_share"], 0.0, 0.15),
        "s_consistency": 0.5 * c(s["drain_length"], 90, 270) + 0.5 * c(s["evenness"], 0.3, 0.7),
    }


def load(path: Path | None = None) -> VariantTable | None:
    """The table shipped with the pool (or the one ``OSU_COACH_VARIANTS`` names), when it is there and made by this
    version of the calculations."""
    try:
        table = VariantTable(path or Path(os.environ.get("OSU_COACH_VARIANTS") or TABLE_PATH))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return None
    return table if table.current else None

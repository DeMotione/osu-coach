"""Streams, kept per play and added up: the stream-speed profile (misses and UR per 10-BPM bin) and the
fall-behind cells (precision by note number in long streams)."""

from __future__ import annotations

import dataclasses
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from osu_coach.domain.analysis.notes import HitObjects
from osu_coach.domain.numeric.stats import weighted_quantile
from osu_coach.domain.player.measures.moments import Moments, weighted_mean, weighted_std
from osu_coach.domain.player.records import SpeedRow

UR_MIN_HITS = 10
MIN_RUN = 7
FALL_MIN_RUN = 16
FALL_MAX_POS = 128
LENGTH_GROUPS = ((16, 31, "16–31 notes"), (32, 63, "32–63 notes"), (64, 10**6, "64+ notes"))


@dataclass(frozen=True, slots=True)
class SpeedBin:
    n: int
    misses: int
    aim_misses: int
    hits: int
    hits_not_300: int
    errors: Moments  # hit errors of the bin


@dataclass(frozen=True, slots=True)
class FallCell:
    """Notes at one position of long streams of one BPM bin and length group."""

    rows: int
    misses: int
    hits: int  # hits with an error
    abs_err: float
    err: float
    rel_err: float  # Σ |error| / gap between notes × 100


@dataclass(frozen=True, slots=True)
class StreamSummary:
    speed: Mapping[int, SpeedBin]  # by 10-BPM bin
    fall: Mapping[tuple[int, int, int], FallCell]  # (10-BPM bin, length group, note number in the stream)
    fall_bpm: Mapping[int, Mapping[float, int]]  # by 10-BPM bin: stream BPM of the hits with an error → count
    fall_runs: Mapping[int, int]  # by 10-BPM bin: streams with a hit with an error
    fall_longest: Mapping[int, int]  # by 10-BPM bin: the longest stream


def stream_summary(notes: HitObjects) -> StreamSummary:
    bpm = notes.stream_bpm
    finite = np.isfinite(bpm)
    hit = notes.head_hit
    aim = np.fromiter((r == "aim" for r in notes.miss_reason.tolist()), dtype=bool, count=len(notes))
    speed: dict[int, SpeedBin] = {}
    sel = (notes.run_len >= MIN_RUN) & (notes.run_pos >= 1) & finite
    bins = np.where(finite, np.floor_divide(np.nan_to_num(bpm), 10) * 10, -1).astype(np.int64)
    for b in np.unique(bins[sel]).tolist():
        m = sel & (bins == b)
        h = m & hit
        speed[int(b)] = SpeedBin(
            n=int(m.sum()),
            misses=int((m & ~hit).sum()),
            aim_misses=int((m & ~hit & aim).sum()),
            hits=int(h.sum()),
            hits_not_300=int((h & (notes.head_result != 300)).sum()),
            errors=Moments.of(notes.err_real[h]),
        )
    long = (notes.run_len >= FALL_MIN_RUN) & (notes.run_pos < FALL_MAX_POS)
    group = np.select([notes.run_len <= hi for _, hi, _ in LENGTH_GROUPS], range(len(LENGTH_GROUPS)), -1)
    with_err = hit & ~np.isnan(notes.err_real)
    gap = 15000.0 / np.maximum(np.nan_to_num(bpm, nan=60.0), 60.0)
    fall: dict = {}
    for i in np.flatnonzero(long).tolist():
        key = (int(bins[i]), int(group[i]), int(notes.run_pos[i]))
        c = fall.get(key, [0, 0, 0, 0.0, 0.0, 0.0])
        c[0] += 1
        c[1] += int(not hit[i])
        if with_err[i]:
            e = float(notes.err_real[i])
            c[2] += 1
            c[3] += abs(e)
            c[4] += e
            c[5] += abs(e) / gap[i] * 100
        fall[key] = c
    fall_bpm: dict[int, Counter] = {}
    runs: dict[int, set] = {}
    longest: dict[int, int] = {}
    for i in np.flatnonzero(long).tolist():
        b = int(bins[i])
        longest[b] = max(longest.get(b, 0), int(notes.run_len[i]))
        if with_err[i]:
            fall_bpm.setdefault(b, Counter())[float(bpm[i])] += 1
            runs.setdefault(b, set()).add(int(notes.run_id[i]))
    return StreamSummary(
        speed=speed,
        fall={k: FallCell(*v) for k, v in fall.items()},
        fall_bpm={b: dict(c) for b, c in fall_bpm.items()},
        fall_runs={b: len(r) for b, r in runs.items()},
        fall_longest=longest,
    )


def _ur(parts: list[tuple[Moments, float]]) -> float:
    std, count = weighted_std(parts)
    return 10 * std if count > 5 else math.nan


def speed_profile_rows(parts: list[tuple[StreamSummary, float]], min_objects: int = 20) -> list[dict]:
    """The stream-speed profile: one row per BPM bin of bursts and streams (UR, miss rate, notes, plays), without
    the trend columns."""
    rows = []
    for b in sorted({b for s, _ in parts for b in s.speed}):
        cells = [(s.speed[b], w) for s, w in parts if b in s.speed]
        n = sum(c.n for c, _ in cells)
        wn = sum(w * c.n for c, w in cells)
        if n < min_objects or wn < min_objects:
            continue
        wh = sum(w * c.hits for c, w in cells)
        miss = sum(w * c.misses for c, w in cells)
        aim = sum(w * c.aim_misses for c, w in cells)
        errors = [(c.errors, w) for c, w in cells]
        plays = [(_ur([(c.errors, w)]), w * c.errors.n) for c, w in cells if c.errors.n >= UR_MIN_HITS]
        pooled = _ur(errors)
        if plays:
            ur = weighted_quantile([u for u, _ in plays], [x for _, x in plays], 0.5)
            best = float(min(u for u, _ in plays))
        else:
            ur, best = pooled, math.nan
        rows.append(
            {
                "bpm_bin": int(b),
                "objects": float(wn),
                "miss_rate": miss / wn,
                "tap_miss_rate": (miss - aim) / wn,
                "speed_aim_rate": aim / wn,
                "non300_rate": sum(w * c.hits_not_300 for c, w in cells) / wh if wh > 0 else math.nan,
                "ur": ur,
                "ur_best": best,
                "ur_plays": len(plays),
                "ur_pooled": pooled,
                "mean_err": weighted_mean(errors) if wh > 0 else math.nan,
            }
        )
    return rows


STREAM_BIN = 4
SPEED_BAND = 30
FALL_MIN_START = 12
FALL_MIN_SLOPE = 0.1
FALL_MIN_GROWTH = 3.0
FALL_MIN_GROWTH_SHARE = 0.2


def fall_behind(parts: list[tuple[StreamSummary, float]], reach_bpm: float | None, min_notes: int = 10) -> dict:
    """How timing falls behind along long streams (by note position, per length group and per BPM band) and where
    it starts, from per-play summaries; the curves are lists of
    rows."""
    out = {
        "curves": [], "curve": [], "start_note": None, "start_seconds": None, "bpm": None, "slope_after": math.nan,
        "growth_ms": math.nan, "base_ms": math.nan, "streams": 0, "longest": 0, "comfort_notes": None,
        "practice_notes": None, "reach_bpm": reach_bpm, "curves_bpm": [],
    }  # fmt: skip
    limit = None if not reach_bpm else reach_bpm + 10
    keep = [(k, c, w) for s, w in parts for k, c in s.fall.items() if limit is None or 0 <= k[0] < limit]
    if sum(c.hits for _, c, _ in keep) < 60:
        return out
    bins_kept = {k[0] for k, _, _ in keep}
    out["streams"] = sum(n for s, _ in parts for b, n in s.fall_runs.items() if b in bins_kept)
    out["longest"] = max((n for s, _ in parts for b, n in s.fall_longest.items() if b in bins_kept), default=0)

    def rows(cells, label_of, pos_of, rel: bool):
        acc: dict = {}
        for k, c, w in cells:
            r = acc.setdefault((label_of(k), pos_of(k)), [0.0, 0.0, 0.0, 0.0, 0.0, 0])
            r[0] += w * c.rows
            r[1] += w * c.misses
            r[2] += w * c.hits
            r[3] += w * (c.rel_err if rel else c.abs_err)
            r[4] += w * c.err
            r[5] += c.hits
        return acc

    curves = []
    by_group = rows(keep, lambda k: k[1], lambda k: k[2] // STREAM_BIN * STREAM_BIN, False)
    for gi, (_, _, label) in enumerate(LENGTH_GROUPS):
        for (g, pb), r in sorted((x for x in by_group.items() if x[0][0] == gi), key=lambda x: x[0][1]):
            if r[5] < min_notes:
                continue
            curves.append({"group": label, "pos": int(pb) + 1, "abs_err": r[3] / r[2], "err": r[4] / r[2],
                           "miss_rate": r[1] / r[0], "n": int(r[5])})  # fmt: skip
    out["curves"] = curves
    banded = [(k, c, w) for k, c, w in keep if k[0] >= 0]
    by_band = rows(banded, lambda k: k[0] // SPEED_BAND * SPEED_BAND, lambda k: k[2] // STREAM_BIN * STREAM_BIN, True)
    by_band_abs = rows(
        banded, lambda k: k[0] // SPEED_BAND * SPEED_BAND, lambda k: k[2] // STREAM_BIN * STREAM_BIN, False
    )
    out["curves_bpm"] = [
        {"group": f"{int(b)}–{int(b) + SPEED_BAND - 1} BPM", "pos": int(pb) + 1, "rel_err": r[3] / r[2],
         "abs_err": by_band_abs[(b, pb)][3] / r[2], "miss_rate": r[1] / r[0], "n": int(r[5])}
        for (b, pb), r in sorted(by_band.items()) if r[5] >= min_notes
    ]  # fmt: skip
    per_pos = rows(keep, lambda k: 0, lambda k: k[2], False)
    g = [(pos, r) for (_, pos), r in sorted(per_pos.items(), key=lambda x: x[0][1]) if r[5] >= min_notes and r[2] > 0]
    if len(g) < 6:
        return out
    x = np.array([pos + 1 for pos, _ in g], dtype=float)
    y = np.array([r[3] / r[2] for _, r in g])
    cw = np.array([r[2] for _, r in g])
    out["curve"] = [
        {"pos": int(p), "abs_err": a, "err": r[4] / r[2], "n": int(r[5])} for p, a, (_, r) in zip(x, y, g, strict=True)
    ]
    bpm_values, bpm_weights = [], []
    for s, w in parts:
        for b, counts in s.fall_bpm.items():
            if b in bins_kept:
                for v, n in counts.items():
                    bpm_values.append(v)
                    bpm_weights.append(w * n)
    bpm = weighted_quantile(bpm_values, bpm_weights, 0.5)
    out["bpm"] = None if math.isnan(bpm) else float(bpm)
    sw = np.sqrt(cw)
    best = None
    for k in x[2:-3]:
        if k < FALL_MIN_START:
            continue
        h = np.maximum(0.0, x - k)
        X = np.column_stack([np.ones_like(x), h])
        coef, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
        sse = float((cw * (y - X @ coef) ** 2).sum())
        if best is None or sse < best[0]:
            best = (sse, float(k), float(coef[0]), float(coef[1]))
    out["comfort_notes"] = int(x.max())
    if best is not None:
        _, k, base, slope = best
        out["slope_after"], out["base_ms"] = slope, base
        out["growth_ms"] = slope * (x.max() - k) if slope > 0 else 0.0
        if (
            slope >= FALL_MIN_SLOPE
            and out["growth_ms"] >= FALL_MIN_GROWTH
            and out["growth_ms"] >= FALL_MIN_GROWTH_SHARE * max(base, 1.0)
        ):
            out["start_note"] = int(k)
            out["comfort_notes"] = int(k)
            if out["bpm"]:
                out["start_seconds"] = (k - 1) * 15.0 / out["bpm"]
    c = out["comfort_notes"]
    out["practice_notes"] = (int(c), int(max(c + 8, round(c * 1.5))))
    return out


WEAK_UR_FACTOR = 1.15  # a BPM whose UR is this much above the trend (and 15+ UR) is a weak spot
WEAK_UR_MIN = 15.0


def ur_trend(rows: Sequence[SpeedRow]) -> np.ndarray:
    """The UR expected at each stream speed: a weighted straight line through the per-BPM URs, never
    falling with speed (faster streams are not easier), fitted again without the bins far above the first
    line so a weak BPM doesn't pull the line up. Bins far above it are BPMs you are weak at."""
    bpm = np.array([r.bpm_bin for r in rows], dtype=float)
    ur = np.array([r.ur for r in rows], dtype=float)
    ok = ~np.isnan(ur)
    if ok.sum() < 3:
        return np.full(len(rows), math.nan)
    x, y = bpm[ok], ur[ok]
    w = np.sqrt(np.maximum(np.array([r.objects for r in rows], dtype=float)[ok], 1))

    def fit(mask):
        slope, icpt = np.polyfit(x[mask], y[mask], 1, w=w[mask])
        if slope < 0:
            slope, icpt = 0.0, float(np.average(y[mask], weights=w[mask]))
        return slope, icpt

    slope, icpt = fit(np.ones(len(x), bool))
    keep = y <= (icpt + slope * x) * WEAK_UR_FACTOR
    if keep.sum() >= 3 and not keep.all():
        slope, icpt = fit(keep)
    return icpt + slope * bpm


def speed_profile(parts: list[tuple[StreamSummary, float]]) -> tuple[SpeedRow, ...]:
    """The stream-speed profile (BPM bins, slowest first) with the UR trend and the weak speeds."""
    rows = [SpeedRow(**r) for r in speed_profile_rows(parts)]
    trend = ur_trend(rows)
    return tuple(
        dataclasses.replace(
            r,
            ur_trend=float(t),
            weak=bool(r.ur > t * WEAK_UR_FACTOR and r.ur - t >= WEAK_UR_MIN),
        )
        for r, t in zip(rows, trend, strict=True)
    )


def stream_limits(rows: Sequence[SpeedRow], base_ur: float) -> dict:
    """Stream speed the player taps cleanly (``comfort_bpm``: ≤ 3% finger misses, UR within 1.6× the
    single-note UR) and where tapping breaks down (``limit_bpm``: ≥ 8% finger misses). Aim misses in
    streams (cursor fell behind) are left out: they are a speed-aim problem, not a tapping-speed one."""
    out: dict = {"comfort_bpm": None, "limit_bpm": None}
    good = [
        r.bpm_bin
        for r in rows
        if r.objects >= 30 and r.tap_miss_rate <= 0.03 and (r.ur <= 1.6 * base_ur or math.isnan(base_ur))
    ]
    if good:
        out["comfort_bpm"] = int(max(good))
    above = [r.bpm_bin for r in rows if r.objects >= 30 and r.tap_miss_rate >= 0.08]
    if out["comfort_bpm"] is not None:
        above = [b for b in above if b > out["comfort_bpm"]]
    if above:
        out["limit_bpm"] = int(min(above))
    return out

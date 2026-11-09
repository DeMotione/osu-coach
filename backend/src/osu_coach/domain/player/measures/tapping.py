"""Tapping: UR, stream speed profile, falling behind in streams, extra presses; the per-play clean stream speed the
ratings use (``ratings.py``)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from osu_coach.domain.analysis.notes import HitObjects, KeyPresses
from osu_coach.domain.numeric.stats import weighted_quantile
from osu_coach.domain.player.measures.moments import Moments, weighted_mean, weighted_std

UR_MIN_HITS = 10  # hits of one play in a BPM bin needed for that play's UR there


STREAM_BIN = 4  # notes per point on the chart


SPEED_BAND = 30  # BPM per band in "stamina in long streams" by speed


# ------------------------------------------------------------------ tapping speed
SPEED_FINGER = ("no_tap", "early", "late", "notelock")  # finger misses (aim / lost-track misses don't count)
SPEED_TIMING = 0.8  # a clean run: no finger miss and 80%+ of its hit notes as 300s (mashing gives 100s)
SPEED_RUNS = 3  # a play's speed: the 3rd fastest clean burst / stream (one lucky burst doesn't decide)


# ------------------------------------------------------------------ hit timing, kept per play and added up
@dataclass(frozen=True, slots=True)
class TimingSummary:
    """One play's hit timing: errors of all / single / stream notes, early hits, single-note 300s, timing misses,
    and the moments of the error against the position in long runs (falling behind)."""

    hit_errors: Moments
    single_errors: Moments
    stream_errors: Moments
    early_hits: int
    single_hits: int
    single_300s: int
    misses: int
    timing_misses: int
    drift_n: int = 0  # hits with an error in runs of 8+ notes: x = position in the run, y = error
    drift_x: float = 0.0
    drift_y: float = 0.0
    drift_xy: float = 0.0
    drift_xx: float = 0.0
    drift_late: Moments = Moments()  # errors in the second half of those runs
    drift_early: Moments = Moments()


def timing_summary(notes: HitObjects) -> TimingSummary:
    hit = notes.head_hit
    errs = np.where(hit, notes.err_real, np.nan)
    single = notes.run_len < 3
    reasons = notes.miss_reason[~hit].tolist()
    long = (notes.run_len >= 8) & hit & ~np.isnan(notes.err_real)
    x = notes.run_pos[long].astype(np.float64)
    y = notes.err_real[long]
    half = notes.run_pos[long] >= notes.run_len[long] / 2
    return TimingSummary(
        hit_errors=Moments.of(errs),
        single_errors=Moments.of(errs[single]),
        stream_errors=Moments.of(errs[~single]),
        early_hits=int((errs < 0).sum()),
        single_hits=int((single & hit).sum()),
        single_300s=int((single & hit & (notes.head_result == 300)).sum()),
        misses=int((~hit).sum()),
        timing_misses=sum(r in ("early", "late") for r in reasons),
        drift_n=int(long.sum()),
        drift_x=float(x.sum()),
        drift_y=float(y.sum()),
        drift_xy=float((x * y).sum()),
        drift_xx=float((x * x).sum()),
        drift_late=Moments.of(y[half]),
        drift_early=Moments.of(y[~half]),
    )


def timing_metrics(parts: list[tuple[TimingSummary, float]]) -> dict:
    """The hit-timing numbers of the tapping page from per-play summaries (``(summary, weight)``)."""

    def ur(field: str) -> float:
        std, count = weighted_std([(getattr(t, field), w) for t, w in parts])
        return 10 * std if count > 5 else math.nan

    errs = [(t.hit_errors, w) for t, w in parts]
    n_err = sum(w * t.hit_errors.n for t, w in parts)
    singles = sum(w * t.single_hits for t, w in parts)
    misses = sum(w * t.misses for t, w in parts)
    out = {
        "ur": ur("hit_errors"),
        "ur_single": ur("single_errors"),
        "ur_streams": ur("stream_errors"),
        "mean_error": weighted_mean(errs),
        "early_share": sum(w * t.early_hits for t, w in parts) / n_err if n_err > 0 else math.nan,
        "three_hundred_rate_single": sum(w * t.single_300s for t, w in parts) / singles if singles > 0 else math.nan,
        "timing_miss_share": sum(w * t.timing_misses for t, w in parts) / misses if misses > 0 else math.nan,
    }
    count = sum(t.drift_n for t, _ in parts)
    sw = sum(w * t.drift_n for t, w in parts)
    if count < 60 or sw < 60:
        out.update(slope_ms_per_note=math.nan, late_half_err=math.nan, early_half_err=math.nan, n=count)
        return out
    sx = sum(w * t.drift_x for t, w in parts)
    sy = sum(w * t.drift_y for t, w in parts)
    sxy = sum(w * t.drift_xy for t, w in parts)
    sxx = sum(w * t.drift_xx for t, w in parts)
    denominator = sw * sxx - sx * sx
    out.update(
        slope_ms_per_note=(sw * sxy - sx * sy) / denominator if denominator else math.nan,
        late_half_err=weighted_mean([(t.drift_late, w) for t, w in parts]),
        early_half_err=weighted_mean([(t.drift_early, w) for t, w in parts]),
        n=int(round(sw)),
    )
    return out


# ------------------------------------------------------------------ key presses, kept per play and added up
LEGACY_KEYS = ("K1", "K2", "M1", "M2")


@dataclass(frozen=True, slots=True)
class PressSummary:
    """One play's key presses: counts by key, alternation, holds, chatter, presses that hit nothing, and the press
    lengths (real time) for the medians."""

    presses: int
    keys: Mapping[str, int]
    in_run: int  # presses aimed at notes of bursts and streams
    in_run_alternated: int
    singles: int  # presses on jumps / singles less than 400 ms after the previous one
    singles_alternated: int
    overlaps: int  # in runs: the key still held when the next press lands
    chatter: int  # the same key again within 20 ms
    extra: int  # presses near a note that hit nothing (not inside a slider or spinner)
    played: int  # played notes (the base of ``extra``)
    durations: np.ndarray  # press length, ms real time
    run_durations: np.ndarray
    run_holds: np.ndarray  # hold ratio of presses in runs


def press_summary(notes: HitObjects, presses: KeyPresses, rate: float) -> PressSummary:
    rate = rate or 1.0
    in_run = presses.target_run_len >= 3
    pattern = presses.target_pattern.tolist()
    singles = np.fromiter((p in ("jump", "single", "spaced") for p in pattern), dtype=bool, count=len(presses))
    singles &= presses.gap_prev < 400
    alternated = presses.alternated.astype(bool)
    next_gap = np.append(presses.time[1:] - presses.time[:-1], np.nan)
    overlap = (presses.duration > next_gap) & in_run
    duration = presses.duration / rate
    keys: dict[str, int] = {}
    for k in presses.key.tolist():
        if k is None:
            continue
        keys[k] = keys.get(k, 0) + 1
    extra = 0
    objects = notes.take(notes.kind != "spinner")
    nothing = presses.time[np.fromiter((o == "none" for o in presses.outcome.tolist()), dtype=bool, count=len(presses))]
    if len(nothing) and len(objects):
        starts = objects.time
        sliders = objects.take(objects.kind == "slider")
        spinners = notes.take(notes.kind == "spinner")
        for t in nothing.tolist():
            j = int(np.searchsorted(starts, t))
            near = min(abs(t - starts[j]) if j < len(starts) else 1e9, abs(t - starts[j - 1]) if j > 0 else 1e9)
            if near > 150:
                continue
            if len(sliders) and np.any((sliders.time < t) & (t <= sliders.end_time)):
                continue
            if len(spinners) and np.any((spinners.time <= t) & (t <= spinners.end_time)):
                continue
            extra += 1
    return PressSummary(
        presses=len(presses),
        keys=keys,
        in_run=int(in_run.sum()),
        in_run_alternated=int((in_run & alternated).sum()),
        singles=int(singles.sum()),
        singles_alternated=int((singles & alternated).sum()),
        overlaps=int(overlap.sum()),
        chatter=int((presses.same_key_gap <= 20).sum()),
        extra=extra,
        played=int(objects.played.sum()),
        durations=duration,
        run_durations=duration[in_run],
        run_holds=presses.hold_ratio[in_run],
    )


def press_metrics(parts: list[tuple[PressSummary, float]]) -> dict:
    """The key-press part of the tapping numbers from per-play summaries (``(summary, weight)``)."""
    total = sum(p.presses for p, _ in parts)
    if not total:
        return {}
    wtotal = sum(w * p.presses for p, w in parts)
    keys: dict[str, float] = {}
    for p, w in parts:
        for k, n in p.keys.items():
            keys[k] = keys.get(k, 0.0) + w * n
    legacy_n = sum(n for p, _ in parts for k, n in p.keys.items() if k in LEGACY_KEYS)
    legacy_w = sum(w for k, w in keys.items() if k in LEGACY_KEYS)
    mouse_w = sum(w for k, w in keys.items() if k in ("M1", "M2"))
    in_run = sum(p.in_run for p, _ in parts)
    in_run_w = sum(w * p.in_run for p, w in parts)
    singles = sum(p.singles for p, _ in parts)
    singles_w = sum(w * p.singles for p, w in parts)

    def joined(field: str) -> tuple[np.ndarray, np.ndarray]:
        values = [getattr(p, field) for p, _ in parts]
        weights = [np.full(len(v), w) for v, (_, w) in zip(values, parts, strict=True)]
        return np.concatenate(values), np.concatenate(weights)

    durations, dw = joined("durations")
    run_durations, rdw = joined("run_durations")
    holds, hw = joined("run_holds")
    played = sum(w * p.played for p, w in parts)
    return {
        "key_share": {k: v / wtotal for k, v in keys.items()} if wtotal > 0 else {},
        "mouse_button_share": mouse_w / legacy_w if legacy_n >= 200 and legacy_w > 0 else math.nan,
        "key_device_known_share": legacy_w / wtotal if wtotal > 0 else math.nan,
        "alternation_in_streams": sum(w * p.in_run_alternated for p, w in parts) / in_run_w
        if in_run > 30
        else math.nan,
        "alternation_singles": sum(w * p.singles_alternated for p, w in parts) / singles_w
        if singles > 30
        else math.nan,
        "press_ms_median": weighted_quantile(durations, dw, 0.5),
        "press_ms_streams": weighted_quantile(run_durations, rdw, 0.5) if in_run else math.nan,
        "hold_ratio_streams": weighted_quantile(holds, hw, 0.5) if in_run > 30 else math.nan,
        "overlap_in_streams": sum(w * p.overlaps for p, w in parts) / in_run_w if in_run > 30 else math.nan,
        "chatter_per_1000": sum(w * p.chatter for p, w in parts) / max(wtotal, 1e-9) * 1000,
        "extra_presses_per_100": sum(w * p.extra for p, w in parts) / played * 100 if played > 0 else 0.0,
        "press_count": total,
    }

"""The few per-note values the miss model, miss chains, reading, consistency and difficulty levels need, kept per
play (:class:`MissNotes`), and those statistics computed from them."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from osu_coach.domain.analysis.notes import HitObjects
from osu_coach.domain.numeric.arrays import ArrayRecord, Bools, Floats, Ints, Texts

CHAIN_WINDOW = 10  # notes after a miss that count as "after a miss"
TYPICAL_CHAIN_RATIO = 2.0
LEVEL_STEP = 0.25


@dataclass(frozen=True, slots=True)
class MissNotes(ArrayRecord):
    """One item per played note (spinners left out)."""

    eq: Floats  # local difficulty, star-equivalent (the harder of aim and speed strain; the map's stars without)
    aim_eq: Floats
    speed_eq: Floats
    missed: Bools
    reason: Texts  # miss reason
    cause: Texts  # miss cause (aim misses on fast patterns: speed_aim)
    fast: Bools
    after: Bools  # within 10 notes after a miss (notelock misses don't count)
    notelock: Bools  # a notelock miss
    density: Ints
    time_frac: Floats
    ar: Floats  # the play's approach rate (with mods)
    hidden: Bools
    w: Floats  # the play's weight; 1 until the profile sets it

    DEFAULTS: ClassVar = {"w": 1.0}


def miss_notes(
    notes: HitObjects, stars: float, ar: float, hidden: bool, causes: np.ndarray, fast: np.ndarray
) -> MissNotes:
    """The :class:`MissNotes` of one play's played notes."""
    eq = np.fmax(notes.aim_eq, notes.speed_eq)
    eq = np.where(np.isnan(eq), stars, eq)
    missed = ~notes.head_hit
    notelock = missed & np.fromiter((r == "notelock" for r in notes.miss_reason.tolist()), dtype=bool, count=len(notes))
    primary = (missed & ~notelock).astype(np.int64)
    before = np.concatenate([[0], np.cumsum(primary)])
    idx = np.arange(len(notes))
    after = (before[idx] - before[np.maximum(idx - CHAIN_WINDOW, 0)]) > 0
    return MissNotes(
        eq=eq,
        aim_eq=notes.aim_eq,
        speed_eq=notes.speed_eq,
        missed=missed,
        reason=notes.miss_reason,
        cause=causes,
        fast=fast,
        after=after,
        notelock=notelock,
        density=notes.density,
        time_frac=notes.time_frac,
        ar=np.full(len(notes), ar),
        hidden=np.full(len(notes), hidden),
        w=np.ones(len(notes)),
    )


def _sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -35.0, 35.0)))


def fit_miss_model(x: np.ndarray, missed: np.ndarray, w: np.ndarray) -> Callable[[np.ndarray], np.ndarray]:
    """Logistic regression P(miss) = s(a + b·z(x)) weighted by ``w``; returns predict(x) (with ``.coef``)."""
    ok = ~np.isnan(x)
    x, y, sw = x[ok], missed[ok].astype(np.float64), w[ok]
    wsum = float(sw.sum())
    ymiss = float((y * sw).sum())
    base = ymiss / wsum if wsum > 0 else 0.05
    if len(x) < 50 or wsum < 50 or ymiss < 3 or ymiss > wsum - 3:
        return lambda e: np.full(np.shape(e), base)
    mu = float((x * sw).sum() / wsum)
    sd = float(math.sqrt((sw * (x - mu) ** 2).sum() / wsum)) or 1.0
    z = (x - mu) / sd
    X = np.column_stack([np.ones_like(z), z])
    coef = np.array([math.log(max(base, 1e-3) / max(1 - base, 1e-3)), 0.0])
    lam = 1e-3
    for _ in range(50):
        p = _sigmoid(X @ coef)
        g = X.T @ (sw * (p - y)) + lam * coef
        H = X.T @ (X * (sw * p * (1 - p))[:, None]) + lam * np.eye(2)
        step = np.linalg.solve(H, g)
        coef -= step
        if np.abs(step).max() < 1e-8:
            break

    def predict(e):
        return _sigmoid(coef[0] + coef[1] * ((np.asarray(e, dtype=float) - mu) / sd))

    predict.coef = (coef[0], coef[1], mu, sd)  # type: ignore[attr-defined]
    return predict


def _rate(mask: np.ndarray, w: np.ndarray) -> float:
    if not len(mask):
        return math.nan
    s = float(w.sum())
    return float((mask * w).sum() / s) if s > 0 else math.nan


def miss_chain_ratio(m: MissNotes) -> float:
    """Observed / expected misses on the notes after a miss (the model fitted on the other notes), shrunk toward the
    typical 2×; NaN with too few notes."""
    keep = ~m.notelock
    fresh, after = keep & ~m.after, keep & m.after
    if after.sum() < 20 or fresh.sum() < 50 or m.w[after].sum() < 20:
        return math.nan
    model = fit_miss_model(m.eq[fresh], m.missed[fresh], m.w[fresh])
    exp = float(np.nansum(model(m.eq[after]) * m.w[after]))
    obs = float((m.missed[after] * m.w[after]).sum())
    return (obs + 5 * TYPICAL_CHAIN_RATIO) / (exp + 5) if exp > 0 else math.nan


def consistency_metrics(m: MissNotes, accuracies: Sequence[float]) -> dict:
    out: dict = {}
    if not len(m):
        return out
    miss = m.missed * m.w
    out["miss_after_miss_ratio"] = miss_chain_ratio(m)
    end = m.time_frac >= 0.8
    out["end_miss_share"] = float(miss[end].sum() / miss.sum()) if miss.sum() > 0 else 0.0
    out["end_object_share"] = _rate(end, m.w)
    first, second = m.time_frac < 0.5, m.time_frac >= 0.5
    out["first_half_miss_rate"] = _rate(m.missed[first], m.w[first])
    out["second_half_miss_rate"] = _rate(m.missed[second], m.w[second])
    if len(accuracies) >= 3:
        out["accuracy_std"] = float(np.nanstd(np.asarray(accuracies, dtype=float), ddof=1))
    return out


def reading_metrics(m: MissNotes, model) -> dict:
    """Miss rates by approach rate, note density and hidden, and observed / expected misses on those notes."""
    out: dict = {}
    misses = m.missed
    lost = np.fromiter((r == "lost" for r in m.reason.tolist()), dtype=bool, count=len(m))
    out["lost_share"] = _rate(lost[misses], m.w[misses]) if misses.any() else math.nan
    if not len(m):
        return out
    thr = max(4, float(np.quantile(m.density, 0.8)))
    hi = m.density >= thr
    out["dense_miss_rate"] = _rate(misses[hi], m.w[hi])
    out["sparse_miss_rate"] = _rate(misses[~hi], m.w[~hi])
    out["dense_threshold"] = float(thr)
    hi_ar, lo_ar, mid_ar = m.ar >= 9.5, m.ar <= 7, (m.ar > 7) & (m.ar < 9.5)
    out["high_ar_miss_rate"] = _rate(misses[hi_ar], m.w[hi_ar]) if m.w[hi_ar].sum() > 50 else math.nan
    out["low_ar_miss_rate"] = _rate(misses[lo_ar], m.w[lo_ar]) if m.w[lo_ar].sum() > 50 else math.nan
    out["mid_ar_miss_rate"] = _rate(misses[mid_ar], m.w[mid_ar])
    hd = m.hidden
    out["hidden_miss_rate"] = _rate(misses[hd], m.w[hd]) if m.w[hd].sum() > 50 else math.nan
    bins = np.round(m.ar * 2) / 2
    table = []
    for b in np.unique(bins[~np.isnan(bins)]).tolist():
        sel = bins == b
        objects = float(m.w[sel].sum())
        if objects >= 30:
            table.append((b, objects, float((misses[sel] * m.w[sel]).sum()) / objects))
    out["ar_table"] = table

    def ratio(mask: np.ndarray) -> tuple[float, int, float]:
        n = float(m.w[mask].sum())
        if mask.sum() < 150 or n < 150:
            return math.nan, int(round(n)), math.nan
        exp = float(np.nansum(model(m.eq[mask]) * m.w[mask]))
        obs = float((misses[mask] * m.w[mask]).sum())
        return (obs / exp if exp >= 5 else math.nan), int(round(n)), obs

    for name, mask in (("high_ar", hi_ar), ("mid_ar", mid_ar), ("low_ar", lo_ar)):
        out[f"{name}_ratio"], out[f"{name}_n"], out[f"{name}_misses"] = ratio(mask)
    out["dense_ratio"], out["dense_n"], out["dense_misses"] = ratio(hi)
    out["sparse_ratio"], out["sparse_n"], _ = ratio(~hi)
    return out


def aim_split(m: MissNotes, model) -> dict:
    """Aim misses on normal-speed patterns vs speed-aim misses on fast ones, each against the misses the model
    expects there."""
    if not len(m):
        return {}
    out = {}
    for name, mask in (("aim", ~m.fast), ("speed_aim", m.fast)):
        w = m.w[mask]
        out[name] = {
            "notes": float(w.sum()),
            "misses": float(((m.cause[mask] == name) * w).sum()),
            "all_misses": float((m.missed[mask] * w).sum()),
            "expected": float(np.nansum(model(m.eq[mask]) * w)) if mask.any() else 0.0,
        }
    return {"split": out}


def skill_levels(m: MissNotes) -> dict:
    """Aim and speed level: the local difficulty up to which the miss rate stays at 5% or less (bins of 0.25★ with
    40+ notes)."""
    out = {"aim_level": math.nan, "speed_level": math.nan}
    for name, x in (("aim_level", m.aim_eq), ("speed_level", m.speed_eq)):
        ok = ~np.isnan(x)
        v, missed = x[ok], m.missed[ok]
        if len(v) < 300:
            continue
        bins = np.arange(0, v.max() + LEVEL_STEP, LEVEL_STEP)
        k = np.searchsorted(bins, v, side="left") - 1
        valid = (k >= 0) & (k < len(bins) - 1)
        best = None
        for b in np.unique(k[valid]).tolist():
            sel = valid & (k == b)
            if sel.sum() >= 40 and missed[sel].mean() <= 0.05:
                best = b
        if best is not None:
            out[name] = float(bins[best]) + LEVEL_STEP
    return out

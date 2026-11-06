"""Aim: quadrants, directions, distances, angles, click points, the tablet-area regression; the per-play jump aim and
flow aim values the ratings use (``ratings.py``)."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from osu_coach.domain.analysis.notes import HitObjects
from osu_coach.domain.numeric.stats import weighted_quantile
from osu_coach.domain.player.moments import Moments, weighted_mean
from osu_coach.domain.player.records import AimStats

# ------------------------------------------------------------------ jump aim
AIM_TOP = 30  # per play: the 30 fastest jumps (cursor speed needed) set its intensity
AIM_COMBO_POWER = 0.8  # x (your max combo / the map's max combo)^0.8, like osu!'s pp


@dataclass(frozen=True, slots=True)
class Bucket:
    """Notes of one kind (a quadrant, a direction, ...): how many, misses, aim misses, and the moments of the aim
    error (on hits and aim misses) and of over-/undershoot (``along``) and the side error (``cross``)."""

    n: int = 0
    misses: int = 0
    aim_misses: int = 0
    aim_rows: int = 0
    err_dx: Moments = Moments()
    err_dy: Moments = Moments()
    along: Moments = Moments()
    cross: Moments = Moments()


def bucket(notes: HitObjects, mask: np.ndarray) -> Bucket:
    hit = notes.head_hit[mask]
    aim = np.asarray([r == "aim" for r in notes.miss_reason[mask].tolist()], dtype=bool)
    aim_rows = hit | aim
    return Bucket(
        n=int(mask.sum()),
        misses=int((~hit).sum()),
        aim_misses=int(aim.sum()),
        aim_rows=int(aim_rows.sum()),
        err_dx=Moments.of(notes.err_dx[mask][aim_rows]),
        err_dy=Moments.of(notes.err_dy[mask][aim_rows]),
        along=Moments.of(notes.along[mask]),
        cross=Moments.of(notes.cross[mask]),
    )


QUADRANTS = ("top-left", "top-right", "bottom-left", "bottom-right")

DIR8 = ("right", "down-right", "down", "down-left", "left", "up-left", "up", "up-right")

ANGLE_BINS = ((0, 60, "sharp (<60°)"), (60, 120, "medium"), (120, 181, "wide (>120°)"))


@dataclass(frozen=True, slots=True)
class AimSummary:
    """Where on the playfield, in which direction and at which angle the notes were and how they went."""

    quadrants: Mapping[str, Bucket]
    grid: Mapping[int, Bucket]  # 3 × 3 cells, 0–8
    directions: Mapping[str, Bucket]  # notes 1+ circle widths after the previous one, by direction
    angles: Mapping[str, Bucket]  # ... by the angle of the turn


def aim_summary(notes: HitObjects) -> AimSummary:
    spaced = notes.dist_norm >= 1.0
    angles = {}
    for lo, hi, label in ANGLE_BINS:
        angles[label] = bucket(notes, spaced & (notes.angle >= lo) & (notes.angle < hi))
    return AimSummary(
        quadrants={q: bucket(notes, notes.quadrant == q) for q in QUADRANTS},
        grid={int(g): bucket(notes, notes.grid == g) for g in np.unique(notes.grid).tolist()},
        directions={d: bucket(notes, spaced & (notes.dir8 == d)) for d in DIR8},
        angles=angles,
    )


DIST_BINS = (0, 0.5, 1, 1.5, 2, 3, 4, 100)
DIST_LABELS = ("<0.5", "0.5-1", "1-1.5", "1.5-2", "2-3", "3-4", "4+")


@dataclass(frozen=True, slots=True)
class JumpSummary:
    """One play's jumps and aim calibration: counts and values the aim page and the setup tips add up."""

    aim_misses: int  # head misses whose cause is aim
    speed_aim_misses: int
    near_misses: int  # misses within 1.4 radii of the centre
    jumps: int  # notes of jump / spaced patterns
    jump_misses: int
    jump_along: Moments
    jump_along_pct: np.ndarray  # along x radius / distance x 100 of every jump
    hit_aim_err: np.ndarray  # aim error (radii) of every hit
    after_slider: int
    after_slider_misses: int
    spaced_stream: int
    spaced_stream_misses: int
    distances: Mapping[str, Bucket]
    distance_aim_err: Mapping[str, np.ndarray]
    # aim regression: actual = M * asked + b on jumps 1.5+ circle widths apart (least squares moments)
    xtx: np.ndarray  # 3 x 3
    xtex: np.ndarray  # 3
    xtey: np.ndarray  # 3
    ex2: float
    ey2: float
    fit_n: int
    radii: Mapping[float, int]  # circle radius of the fitted jumps -> count


def jump_summary(notes: HitObjects, causes: np.ndarray) -> JumpSummary:
    hit = notes.head_hit
    missed = ~hit
    aim_reason = np.fromiter((r == "aim" for r in notes.miss_reason.tolist()), dtype=bool, count=len(notes))
    jumpy = np.fromiter((p in ("jump", "spaced") for p in notes.pattern.tolist()), dtype=bool, count=len(notes))
    from_slider = notes.from_slider.astype(bool)
    spaced = notes.spaced_stream.astype(bool)
    distances, distance_err = {}, {}
    ok = ~np.isnan(notes.dist_norm)
    for lo, hi, label in zip(DIST_BINS[:-1], DIST_BINS[1:], DIST_LABELS, strict=True):
        m = ok & (notes.dist_norm >= lo) & (notes.dist_norm < hi)
        distances[label] = bucket(notes, m)
        distance_err[label] = notes.aim_err[m].astype(np.float64)
    fit = (hit | aim_reason) & (notes.dist_norm >= 1.5)
    for col in (notes.start_x, notes.start_y, notes.err_dx, notes.err_dy):
        fit &= ~np.isnan(col)
    ix, iy = notes.x[fit] - notes.start_x[fit], notes.y[fit] - notes.start_y[fit]
    X = np.column_stack([ix, iy, np.ones(int(fit.sum()))])
    ex, ey = notes.err_dx[fit], notes.err_dy[fit]
    with np.errstate(invalid="ignore", divide="ignore"):
        pct = notes.along * notes.radius / notes.dist * 100
    return JumpSummary(
        aim_misses=int((causes == "aim").sum()),
        speed_aim_misses=int((causes == "speed_aim").sum()),
        near_misses=int((missed & (notes.miss_dist <= 1.4)).sum()),
        jumps=int(jumpy.sum()),
        jump_misses=int((jumpy & missed).sum()),
        jump_along=Moments.of(notes.along[jumpy]),
        jump_along_pct=pct[jumpy].astype(np.float64),
        hit_aim_err=notes.aim_err[hit].astype(np.float64),
        after_slider=int(from_slider.sum()),
        after_slider_misses=int((from_slider & missed).sum()),
        spaced_stream=int(spaced.sum()),
        spaced_stream_misses=int((spaced & missed).sum()),
        distances=distances,
        distance_aim_err=distance_err,
        xtx=X.T @ X,
        xtex=X.T @ ex,
        xtey=X.T @ ey,
        ex2=float((ex * ex).sum()),
        ey2=float((ey * ey).sum()),
        fit_n=int(fit.sum()),
        radii=dict(Counter(notes.radius[fit].tolist())),
    )


def _joined(parts, field: str) -> tuple[np.ndarray, np.ndarray]:
    values = [getattr(j, field) for j, _ in parts]
    if not values:
        return np.array([]), np.array([])
    weights = [np.full(len(v), w) for v, (_, w) in zip(values, parts, strict=True)]
    return np.concatenate(values), np.concatenate(weights)


def jump_metrics(parts: list[tuple[JumpSummary, float]], notes: float, misses: float) -> dict:
    """The jump part of the profile's aim numbers (notes / misses: weighted played notes and misses)."""

    def wsum(field: str) -> float:
        return sum(w * getattr(j, field) for j, w in parts)

    def rate(num: str, den: str) -> float:
        d = wsum(den)
        return wsum(num) / d if d > 0 else math.nan

    jumps = wsum("jumps")
    pct, pw = _joined(parts, "jump_along_pct")
    err, ew = _joined(parts, "hit_aim_err")
    return {
        "aim_miss_rate": wsum("aim_misses") / notes if notes > 0 else math.nan,
        "aim_miss_share": wsum("aim_misses") / misses if misses > 0 else math.nan,
        "speed_aim_miss_share": wsum("speed_aim_misses") / misses if misses > 0 else math.nan,
        "near_miss_share": wsum("near_misses") / misses if misses > 0 else math.nan,
        "jump_objects": int(round(jumps)),
        "jump_miss_rate": rate("jump_misses", "jumps"),
        "jump_along": weighted_mean([(j.jump_along, w) for j, w in parts]) if jumps else math.nan,
        "jump_along_pct": weighted_quantile(pct, pw, 0.5) if jumps else math.nan,
        "aim_err_median": weighted_quantile(err, ew, 0.5) if notes else math.nan,
        "after_slider_miss_rate": rate("after_slider_misses", "after_slider"),
        "spaced_stream_objects": int(round(wsum("spaced_stream"))),
        "spaced_stream_miss_rate": rate("spaced_stream_misses", "spaced_stream"),
    }


def regression(parts: list[tuple[JumpSummary, float]]) -> dict | None:
    """How the aim on jumps 1.5+ circle widths apart is off: scale, rotation and offset of actual vs asked movement
    (weighted least squares, from per-play moments); None with fewer than 40 jumps."""
    n = sum(w * j.fit_n for j, w in parts)
    if sum(j.fit_n for j, _ in parts) < 40 or n < 40:
        return None
    A = sum(w * j.xtx for j, w in parts)
    bx = sum(w * j.xtex for j, w in parts)
    by = sum(w * j.xtey for j, w in parts)
    cx, cy = np.linalg.solve(A, bx), np.linalg.solve(A, by)
    M = np.array([[1 + cx[0], cx[1]], [cy[0], 1 + cy[1]]])
    U, sig, Vt = np.linalg.svd(M)
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1
        R = U @ Vt
    S = Vt.T @ np.diag(sig) @ Vt
    sse_x = sum(w * j.ex2 for j, w in parts) - 2 * cx @ bx + cx @ A @ cx
    sse_y = sum(w * j.ey2 for j, w in parts) - 2 * cy @ by + cy @ A @ cy
    var = max(float((sse_x + sse_y) / 2 / n), 0.0)
    radii: Counter = Counter()
    for j, _ in parts:
        radii.update(j.radii)
    values = sorted(radii.elements())
    return {
        "n": int(round(n)),
        "scale_x": float(S[0, 0]),
        "scale_y": float(S[1, 1]),
        "rotation_deg": math.degrees(math.atan2(R[1, 0], R[0, 0])),
        "offset_x": float(cx[2]),
        "offset_y": float(cy[2]),
        "offset_se": math.sqrt(var / n),
        "residual_px": math.sqrt(var),
        "radius": float(np.median(values)) if values else 36.5,
    }


# ------------------------------------------------------------------ the tables, added up from per-play summaries
def _stats(name: str | int, buckets: list[tuple[Bucket, float]], aim_err: float = math.nan) -> AimStats:
    n = sum(w * b.n for b, w in buckets)
    misses = sum(w * b.misses for b, w in buckets)
    aim = sum(w * b.aim_misses for b, w in buckets)

    def mean(field: str) -> float:
        return weighted_mean([(getattr(b, field), w) for b, w in buckets])

    return AimStats(
        name=name,
        objects=float(n),
        misses=float(misses),
        miss_rate=misses / n if n > 0 else math.nan,
        aim_misses=float(aim),
        aim_miss_rate=aim / n if n > 0 else math.nan,
        mean_dx=mean("err_dx"),
        mean_dy=mean("err_dy"),
        along=mean("along"),
        cross=mean("cross"),
        aim_err=aim_err,
    )


def quadrant_table(parts: list[tuple[AimSummary, float]]) -> tuple[AimStats, ...]:
    return tuple(_stats(q, [(a.quadrants[q], w) for a, w in parts]) for q in QUADRANTS)


def grid_table(parts: list[tuple[AimSummary, float]]) -> tuple[AimStats, ...]:
    """The 3 × 3 cells 0–8 (a cell without notes: 0 objects)."""
    return tuple(_stats(g, [(a.grid[g], w) for a, w in parts if g in a.grid]) for g in range(9))


def direction_table(parts: list[tuple[AimSummary, float]]) -> tuple[AimStats, ...]:
    return tuple(_stats(d, [(a.directions[d], w) for a, w in parts]) for d in DIR8)


def angle_table(parts: list[tuple[AimSummary, float]]) -> tuple[AimStats, ...]:
    return tuple(_stats(label, [(a.angles[label], w) for a, w in parts]) for _, _, label in ANGLE_BINS)


def distance_table(parts: list[tuple[JumpSummary, float]]) -> tuple[AimStats, ...]:
    rows = []
    for label in DIST_LABELS:
        chunks = [j.distance_aim_err[label] for j, _ in parts]
        err = np.concatenate(chunks) if chunks else np.array([])
        median = float(np.nanmedian(err)) if np.isfinite(err).any() else math.nan
        rows.append(_stats(label, [(j.distances[label], w) for j, w in parts], median))
    return tuple(rows)


def worst_quadrant(quadrants: tuple[AimStats, ...]) -> dict | None:
    """The quadrant missed most, against the others: its miss rate, the relative risk and whether the difference
    is significant (z > 2, 80+ notes, 8+ misses, 1.25× the rest)."""
    q = [r for r in quadrants if r.objects > 0]
    if not q or sum(r.misses for r in q) == 0:
        return None
    rates = [r.miss_rate for r in q]
    row = q[int(np.nanargmax(rates))]
    rest = [r for r in q if r is not row]
    n1, m1 = row.objects, row.misses
    n2, m2 = sum(r.objects for r in rest), sum(r.misses for r in rest)
    p1 = m1 / n1
    p2 = m2 / n2 if n2 else 0.0
    pooled = (m1 + m2) / (n1 + n2)
    se = math.sqrt(max(pooled * (1 - pooled) * (1 / n1 + 1 / max(n2, 1)), 1e-12))
    z = (p1 - p2) / se
    rr = p1 / p2 if p2 > 0 else math.inf
    return {
        "quadrant": row.name,
        "miss_rate": float(p1),
        "rest_miss_rate": float(p2),
        "relative_risk": float(rr),
        "z": float(z),
        "objects": int(round(n1)),
        "misses": int(round(m1)),
        "mean_dx": float(row.mean_dx),
        "mean_dy": float(row.mean_dy),
        "along": float(row.along),
        "aim_miss_rate": float(row.aim_miss_rate),
        "significant": bool(z > 2.0 and n1 >= 80 and m1 >= 8 and rr >= 1.25),
    }

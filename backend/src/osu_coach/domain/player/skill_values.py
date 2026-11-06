"""What one play shows of each rated skill: aim and flow-aim intensity, clean stream speed, slider difficulty,
reading demand and the stamina tempo curve, from the play's played notes (:class:`HitObjects`) and a few facts about
the play (:class:`PlayContext`)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from osu_coach.domain.analysis.notes import HitObjects
from osu_coach.domain.player.aim import AIM_COMBO_POWER, AIM_TOP
from osu_coach.domain.player.reading import (
    READ_ACC_POWER,
    READ_AR_HIGH_STEP,
    READ_AR_MIN,
    READ_AR_STEP,
    READ_BPM_BONUS,
    READ_BPM_FULL,
    READ_BPM_JUMP,
    READ_BPM_NOTES,
    READ_FL,
    READ_HD,
    READ_NPS,
    READ_NPS_RANGE,
    usual_ar,
)
from osu_coach.domain.player.stamina import PRESSED_REASONS, STAMINA_KEPT, STAMINA_KEPT_ZERO, STAMINA_WINDOWS
from osu_coach.domain.player.tapping import SPEED_FINGER, SPEED_RUNS, SPEED_TIMING

FLOW_TOP = 50  # per play: the 50 fastest spaced-stream notes set its cursor speed
FLOW_AMOUNT = 100.0  # spaced-stream notes for the full amount: ×(notes / 100)^0.25, 0.6–1.5
FLOW_AMOUNT_RANGE = (0.6, 1.5)
SLIDER_FOLLOW_SLACK = 1.0  # circle diameters of slider path the follow circle covers without moving
SLIDER_SHORT = 0.5  # ... short sliders still count as half a diameter of movement (holding them)


@dataclass(frozen=True, slots=True)
class PlayContext:
    """The facts about a play the skill values read besides its notes."""

    key: str
    map: str  # its map / mod setup (repeated plays of one setup count once)
    completed: bool = True
    combo_ratio: float = math.nan  # max combo / the map's
    ar: float = math.nan  # with mods
    accuracy: float = math.nan
    stars: float = math.nan
    rate: float = 1.0
    hidden: bool = False
    hidden_custom: bool = False  # hidden with custom fade settings
    flashlight: bool = False


@dataclass(frozen=True, slots=True)
class AimValue:
    intensity: float  # average cursor speed of the 30 fastest jumps (circle diameters per real second)
    combo: float
    value: float  # intensity × combo^0.8
    jumps: int


@dataclass(frozen=True, slots=True)
class FlowValue:
    speed: float  # average cursor speed of the 50 fastest spaced-stream notes
    amount: float  # (spaced-stream notes / 100)^0.25, 0.6–1.5
    combo: float
    value: float  # speed × amount × combo^0.8
    notes: int


@dataclass(frozen=True, slots=True)
class SpeedValue:
    bpm: float  # the 3rd fastest clean burst / stream; NaN with fewer clean runs
    runs: int
    clean: int


@dataclass(frozen=True, slots=True)
class ReadingValue:
    ar: float
    nps: float
    ar_factor: float
    bpm_changes: int
    bpm_hit: float
    bpm_factor: float
    accuracy: float
    value: float  # ar_factor × bpm_factor × accuracy^8


def _isin(texts: np.ndarray, values: tuple[str, ...]) -> np.ndarray:
    return np.fromiter((t in values for t in texts.tolist()), dtype=bool, count=len(texts))


def _combo(ctx: PlayContext) -> float:
    c = ctx.combo_ratio
    return 1.0 if c is None or not math.isfinite(c) else float(c)


def top(values: np.ndarray, n: int) -> np.ndarray:
    """Indices of the ``n`` largest values (NaN left out; ties: the first ones), largest first."""
    idx = np.flatnonzero(~np.isnan(values))
    order = np.argsort(-values[idx], kind="stable")
    return idx[order[:n]]


def cursor_speed(notes: HitObjects, clip: bool = True) -> np.ndarray:
    """Cursor speed to each note: circle diameters per real second."""
    radius = np.maximum(notes.radius, 1.0) if clip else notes.radius
    return notes.velocity_real * 1000.0 / (2 * radius)


def jumps_mask(notes: HitObjects) -> np.ndarray:
    return _isin(notes.pattern, ("jump", "spaced"))


def flow_mask(notes: HitObjects) -> np.ndarray:
    return notes.spaced_stream.astype(bool) & (notes.run_pos > 0)


def aim_value(notes: HitObjects, ctx: PlayContext) -> AimValue | None:
    """Aim of a passed play: the average cursor speed of its 30 fastest jumps × (max combo / the map's)^0.8 (like
    osu!'s pp, a hard map only counts fully when you hold the combo)."""
    if not ctx.completed:
        return None
    v = cursor_speed(notes)[jumps_mask(notes)]
    v = v[~np.isnan(v)]
    if len(v) < 10:
        return None
    intensity = float(v[top(v, AIM_TOP)].mean())
    c = _combo(ctx)
    return AimValue(intensity, c, intensity * c**AIM_COMBO_POWER, len(v))


def flow_value(notes: HitObjects, ctx: PlayContext) -> FlowValue | None:
    """Flow aim of a passed play: the average cursor speed of its 50 fastest spaced-stream notes (bursts / streams
    0.9+ circle widths apart) × amount (spaced-stream notes / 100)^0.25 × combo^0.8."""
    if not ctx.completed:
        return None
    v = cursor_speed(notes)[flow_mask(notes)]
    v = v[~np.isnan(v)]
    if len(v) < 20:
        return None
    speed = float(v[top(v, FLOW_TOP)].mean())
    amount = float(np.clip((len(v) / FLOW_AMOUNT) ** 0.25, *FLOW_AMOUNT_RANGE))
    c = _combo(ctx)
    return FlowValue(speed, amount, c, speed * amount * c**AIM_COMBO_POWER, len(v))


def speed_value(notes: HitObjects) -> SpeedValue | None:
    """The speed you tap bursts and streams (3+ notes) cleanly: the 3rd fastest run with no finger miss (no tap,
    too early / late, notelock; cursor misses don't count) and 80%+ of its hit notes as 300s."""
    keep = (notes.run_id >= 0) & (notes.run_len >= 3) & ~np.isnan(notes.stream_bpm)
    if not keep.any():
        return None
    run = notes.run_id[keep]
    bpm = notes.stream_bpm[keep]
    hit = notes.head_hit[keep]
    finger = ~hit & _isin(notes.miss_reason[keep], SPEED_FINGER)
    great = (notes.head_result[keep] == 300) & hit
    ids, first, inverse = np.unique(run, return_index=True, return_inverse=True)
    n_finger = np.bincount(inverse, weights=finger, minlength=len(ids))
    n_hit = np.bincount(inverse, weights=hit, minlength=len(ids))
    n_great = np.bincount(inverse, weights=great, minlength=len(ids))
    clean = (n_finger == 0) & (n_great >= SPEED_TIMING * np.maximum(n_hit, 1))
    fastest = np.sort(bpm[first][clean])[::-1]
    return SpeedValue(
        float(fastest[SPEED_RUNS - 1]) if len(fastest) >= SPEED_RUNS else math.nan, len(ids), int(clean.sum())
    )


def slider_difficulty(notes: HitObjects) -> np.ndarray:
    """Difficulty of following each slider (0 = the follow circle covers it without moving):

    speed (circle diameters per second the ball moves, real time) × length (log2 of 1 + the path beyond what
    the follow circle covers, in diameters; repeats add log2(repeats)) × shape (1 + half a point per half
    circle of turning, up to 2 full turns, + 0.3 per sharp corner and + 0.2 per left↔right bend, up to 4 each)
    × speed change (1 + |ln(speed / previous slider's speed)|, up to ×2: a slow slider right after a fast one or
    the other way round) × rush (up to ×1.5 when the next note comes less than 250 ms after the slider end)."""

    def col(values: np.ndarray, fill: float = 0.0) -> np.ndarray:
        values = np.asarray(values, dtype=np.float64)
        return np.where(np.isnan(values), fill, values)

    diam = 2 * np.maximum(notes.radius, 1.0)
    speed = col(notes.slider_vel_real) * 1000.0 / diam
    eff = np.maximum(col(notes.slider_len) / diam - SLIDER_FOLLOW_SLACK, 0)
    spans = np.maximum(col(notes.slider_spans, 1.0), 1)
    length = np.log2(1 + (eff + SLIDER_SHORT) * (1 + np.log2(spans)))
    shape = (
        1
        + 0.5 * np.minimum(col(notes.slider_turn) / math.pi, 4)
        + 0.3 * np.minimum(col(notes.slider_corners), 4)
        + 0.2 * np.minimum(col(notes.slider_bends), 4)
    )
    change = 1 + np.minimum(col(notes.slider_vel_change), 1.0)
    rush = 1 + 0.5 * np.clip((250.0 - col(notes.slider_next_gap, 1000.0)) / 250.0, 0, 1)
    return speed * length * shape * change * rush


def reading_value(notes: HitObjects, ctx: PlayContext) -> ReadingValue | None:
    """Reading demand × how well you played it (passed plays):

    * ``ar_factor`` = 2^((usual AR for the map's stars − its AR with mods) / 3 × ``busy``): AR 3 lower than
      usual = ×2, 6 lower = ×4 on a map with 5 circles per second; ``busy`` = circles per second ÷ 5 (during
      play, breaks of 5+ s left out; 0.25–2), so low AR on a slow map counts much less than on a busy one (higher
      AR than usual: down to 0.6); × 1.2 with hidden, × 1.6 with flashlight;
    * ``bpm_factor`` = 1 + 0.5 × min(1, BPM changes ÷ 8) × your 300 share on the first 4 notes after each
      change (a miss = 0): read and hit the BPM changes accurately and a map full of them counts ×1.5;
    * ``value`` = ar_factor × bpm_factor × accuracy^8 (decent accuracy on those maps: 95% = 0.66).

    Hidden with custom fade settings has a visibility curve this estimate does not model: no value."""
    if not ctx.completed or ctx.hidden_custom:
        return None
    d = notes.take(notes.kind != "spinner")
    ar, acc = float(ctx.ar), float(ctx.accuracy)
    if not (math.isfinite(ar) and math.isfinite(acc)) or len(d) < 30:
        return None
    d = d.take(np.argsort(d.time, kind="stable"))
    stars = float(ctx.stars) if math.isfinite(ctx.stars) else 6.0
    tt = d.time.astype(np.float64) / (ctx.rate or 1.0) / 1000.0
    gaps = np.diff(tt)
    active = float(gaps[(gaps > 0) & (gaps <= 5.0)].sum())
    nps = len(tt) / active if active > 0 else READ_NPS
    busy = float(np.clip(nps / READ_NPS, *READ_NPS_RANGE))
    diff = float(usual_ar(stars)) - ar
    f_ar = max(READ_AR_MIN, 2 ** (diff / READ_AR_STEP * busy), 2 ** (-diff / READ_AR_HIGH_STEP * busy))
    if ctx.hidden:
        f_ar *= READ_HD
    if ctx.flashlight:
        f_ar *= READ_FL
    b = d.bpm_real.astype(np.float64)
    with np.errstate(invalid="ignore"):
        jump = np.r_[False, np.abs(np.diff(b)) / np.maximum(b[:-1], 1e-6) > READ_BPM_JUMP]
    starts = np.flatnonzero(jump)
    after = np.zeros(len(d), dtype=bool)
    for i in starts:
        after[i : i + READ_BPM_NOTES] = True
    hit = float((d.head_result[after] == 300).mean()) if after.any() else math.nan
    f_bpm = 1.0 + READ_BPM_BONUS * min(1.0, len(starts) / READ_BPM_FULL) * (hit if hit == hit else 0.0)
    return ReadingValue(ar, nps, f_ar, len(starts), hit, f_bpm, acc, f_ar * f_bpm * max(acc, 0.0) ** READ_ACC_POWER)


def tempo_curve(notes: HitObjects, rate: float = 1.0, windows=STAMINA_WINDOWS, all_pressed: bool = False) -> dict:
    """Stamina curve of a play: for each duration W (seconds), the fastest tempo you kept up for W seconds.

    Every note you tap (circles and slider heads, not spinners) counts if you pressed a key for it — 300s, 100s,
    50s and misses where you tapped (also too early: overstreaming); only notes you didn't press for (no tap,
    lost, not reached) don't. In every W-second stretch of the play: tempo = pressed notes per second as 1/4-note
    BPM (15 × notes per second, so a 220 BPM stream = 220), × the kept share (pressed 90%+ of the notes there =
    1, 60% or less = 0, linear between): when your fingers start to give in (undertapping), the tempo stops
    counting. Only stretches inside what you played count, and a play shorter than W has no value for W.
    ``all_pressed``: as if every note was pressed (what the notes demand)."""
    d = notes.take(notes.kind != "spinner")
    if len(d) < 2:
        return {}
    pressed = np.ones(len(d), dtype=bool) if all_pressed else d.head_hit | _isin(d.miss_reason, PRESSED_REASONS)
    t_all = d.time.astype(np.float64) / (rate if rate == rate and rate else 1.0) / 1000.0
    order = np.argsort(t_all)
    t, pr = t_all[order], pressed[order]
    span = t[-1] - t[0]
    cp = np.concatenate([[0], np.cumsum(pr)])
    idx = np.arange(len(t))
    out = {}
    for W in windows:
        if span < W * 0.98:
            continue
        j = np.searchsorted(t, t + W, side="left")
        n = j - idx
        kept = cp[j] - cp[idx]
        share = np.where(n > 0, kept / np.maximum(n, 1), 0.0)
        q = np.clip((share - STAMINA_KEPT_ZERO) / (STAMINA_KEPT - STAMINA_KEPT_ZERO), 0, 1)
        bpm = np.where(t + W <= t[-1] + 0.02 * W, kept / W * 15.0 * q, 0.0)
        out[int(W)] = float(bpm.max())
    return out

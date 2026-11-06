"""The items of one play (spec §3.0, §6.2): every played note against its difficulty in stars, grouped.

Heads (circles and slider heads) are put in a class by their pattern: J (jumps and spaced singles: aim, reading),
S (streams up to 16 notes: tapping, reading), DEEP (deep in a stream: stamina, reading), F (spaced streams: flow aim,
tapping or stamina, reading). A held slider tests slider control (it breaks or not), a hit single note accuracy
(300 or not). Notes of one class with the same rounded difficulties form a group: how many there were and how many
failed, by miss class A (aim) / B (behind) / T (early, no tap, notelock).

Deviations from the spec (``docs/star-scale-irt.md``): a stream note judged 50 fails its tapping like a miss
(fix 10); stamina also takes stream notes 30 s into a dense tapping section (fix 11); reading counts how many notes
are visible at once (fix 12); sliders count only when their path leaves the follow circle; accuracy uses ``head_result`` and only plays whose timing counts (fix 9).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.analysis.notes import HitObjects
from osu_coach.domain.numeric.arrays import ArrayRecord, Floats, Ints
from osu_coach.domain.player.engines.irt import constants as K
from osu_coach.domain.player.engines.irt import tables
from osu_coach.domain.player.engines.irt.anchors import preempt_ms, star_of

B_COLUMNS = ("b_aim", "b_flow", "b_tap", "b_stam", "b_read", "b_sl")
SL_TOP = 13.0  # ★: the top knot of the slider anchor


@dataclass(frozen=True, slots=True)
class IrtGroups(ArrayRecord):
    """Groups of items: their kind (``HEAD`` / ``SLIDER`` / ``ACCURACY``), the difficulty (★) of every skill they
    test (NaN: not tested), whether they were played late in a session, how many items (``n``, weighted once merged)
    and how many failed by class (sliders: breaks in ``f_a``; accuracy: non-300s in ``f_a``)."""

    kind: Ints
    b_aim: Floats
    b_flow: Floats
    b_tap: Floats
    b_stam: Floats
    b_read: Floats
    b_sl: Floats
    b_acc: Floats
    late: Floats
    n: Floats
    f_a: Floats
    f_b: Floats
    f_t: Floats

    def b(self) -> np.ndarray:
        """The difficulties of the six skills of the joint fit, one column each."""
        return np.column_stack([getattr(self, c) for c in B_COLUMNS]) if len(self) else np.zeros((0, 6))

    def failed(self) -> np.ndarray:
        return self.f_a + self.f_b + self.f_t


def _stars(anchor: str, x: np.ndarray) -> np.ndarray:
    return star_of(x, tables.ANCHORS[anchor])


def _log2(x) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(x > 0, np.log2(np.where(x > 0, x, 1.0)), np.nan)


def _col(values, fill: float = 0.0) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    return np.where(np.isfinite(values), values, fill)


def tapping_time(notes: HitObjects) -> np.ndarray:
    """How long (s, real time) each note is into a dense tapping section: notes at most ``STREAM_GAP_MS`` apart."""
    gaps = _col(notes.dt_real, np.inf)
    out = np.zeros(len(notes))
    run = 0.0
    for i, gap in enumerate(gaps.tolist()):
        run = run + gap if gap <= K.STREAM_GAP_MS else 0.0
        out[i] = run / 1000.0
    return out


def miss_class(notes: HitObjects) -> np.ndarray:
    """A (0), B (1) or T (2) for every note by its miss reason (-1 for hits)."""
    reason = notes.miss_reason
    out = np.full(len(notes), 1, dtype=np.int64)  # late, lost, unknown: behind
    out[np.isin(reason, ["aim", "speed_aim"])] = 0
    out[np.isin(reason, ["early", "no_tap", "notelock"]) | notes.forced_miss.astype(bool)] = 2
    out[notes.head_hit.astype(bool)] = -1
    return out


def slider_stars(notes: HitObjects) -> np.ndarray:
    """``b_sl`` of every slider (§6.2): its speed in circle widths per second, plus its shape and speed change."""
    diam = 2 * np.maximum(_col(notes.radius, 32.0), 1.0)
    # held at the top knot: the anchor knows maps' typical slider speeds (up to ~16 widths/s at 13★), while single
    # sliders of ordinary maps go far faster — extrapolated, they'd read 30★ and more
    speed = np.minimum(_stars("sl", _log2(_col(notes.slider_vel_real, np.nan) * 1000.0 / diam)), SL_TOP)
    shape = (
        1
        + 0.5 * np.minimum(_col(notes.slider_turn) / np.pi, 4)
        + 0.3 * np.minimum(_col(notes.slider_corners), 4)
        + 0.2 * np.minimum(_col(notes.slider_bends), 4)
    )
    change = 1 + np.minimum(_col(notes.slider_vel_change), 1.0)
    return speed + K.K_SL * np.log2(shape * change)


def item_table(notes: HitObjects, meta: ReplayMeta, timing_counts: bool = True) -> dict[str, np.ndarray]:
    """Every item of the played notes (``HitObjects.played_notes``) of one play, ungrouped: one row per head, held
    slider and hit single note (columns as :class:`IrtGroups`, ``fail`` the miss class or -1)."""
    n = len(notes)
    kind_text = notes.kind
    head = np.isin(kind_text, ["circle", "slider"])
    hit = notes.head_hit.astype(bool)
    dist = _col(notes.dist_norm)
    run_len, run_pos = np.asarray(notes.run_len), np.asarray(notes.run_pos)
    b_aim_all = _stars("aim", _log2(notes.aim_eq))
    b_tap_all = _stars("spd", _log2(notes.speed_eq))
    density = np.maximum(_col(notes.density, 1.0), 1.0)
    hidden, flashlight = bool(meta.mods & 8), bool(meta.mods & 1024)
    b_read = (
        _stars("read", -np.log2(preempt_ms(meta.ar)))
        + K.H_HD * hidden
        + K.H_FL * flashlight
        + K.K_DENSITY * np.log2(np.maximum(density / K.DENSITY_REF, 1.0))
    )
    b_read = np.broadcast_to(b_read, (n,)).astype(float)
    deep = (run_pos >= 16) | (tapping_time(notes) >= K.STAMINA_S)
    single = (run_len < 3) | (run_pos == 0)
    in_run = (run_len >= 3) & (run_pos >= 1)
    cls = np.full(n, -1, dtype=np.int64)
    cls[head & single & (dist >= 1)] = K.J
    cls[head & in_run & (dist < 0.9) & ~deep] = K.S
    cls[head & in_run & (dist < 0.9) & deep] = K.DEEP
    cls[head & in_run & (dist >= 0.9)] = K.F
    needs_aim = np.isin(cls, [K.J, K.F])
    needs_tap = np.isin(cls, [K.S, K.DEEP, K.F])
    cls[(needs_aim & ~np.isfinite(b_aim_all)) | (needs_tap & ~np.isfinite(b_tap_all))] = -1

    fail = miss_class(notes)
    # a stream note judged 50 fails its tapping too: late (B) or early (T) by the sign of the hit error
    fifty = np.isin(cls, [K.S, K.DEEP, K.F]) & hit & (np.asarray(notes.head_result) == 50)
    fail[fifty] = np.where(_col(notes.hit_error) > 0, 1, 2)[fifty]

    nan = np.full(n, np.nan)
    heads = cls >= 0
    rows = {
        "kind": np.full(int(heads.sum()), K.HEAD),
        "b_aim": np.where(cls == K.J, b_aim_all, np.nan)[heads],
        "b_flow": np.where(cls == K.F, b_aim_all, np.nan)[heads],
        "b_tap": np.where((cls == K.S) | ((cls == K.F) & ~deep), b_tap_all, np.nan)[heads],
        "b_stam": np.where((cls == K.DEEP) | ((cls == K.F) & deep), b_tap_all, np.nan)[heads],
        "b_read": b_read[heads],
        "b_sl": nan[heads],
        "b_acc": nan[heads],
        "fail": fail[heads],
    }
    held = (kind_text == "slider") & hit
    b_sl = slider_stars(notes)
    # only sliders whose path leaves the follow circle test following: a short fast one (a kick slider) is
    # held without moving, however fast its ball (it would read 30★+ by speed alone)
    diam = 2 * np.maximum(_col(notes.radius, 32.0), 1.0)
    moves = _col(notes.slider_len) / diam > K.SLIDER_FOLLOW_SLACK
    held &= np.isfinite(b_sl) & moves
    sl_rows = {
        "kind": np.full(int(held.sum()), K.SLIDER),
        **{c: nan[held] for c in ("b_aim", "b_flow", "b_tap", "b_stam", "b_read", "b_acc")},
        "b_sl": b_sl[held],
        "fail": np.where(notes.broke.astype(bool), 0, -1)[held],
    }
    singles = head & (run_len < 3) & hit if timing_counts else np.zeros(n, dtype=bool)
    window = _stars("acc", -np.log2(max(79.5 - 6 * float(meta.od), 1.0)))
    local = np.fmax(b_aim_all, b_tap_all)
    b_acc = np.where(np.isfinite(local), window + K.LAMBDA * (local - window), window)
    acc_rows = {
        "kind": np.full(int(singles.sum()), K.ACCURACY),
        **{c: nan[singles] for c in B_COLUMNS},
        "b_acc": b_acc[singles],
        "fail": np.where(np.asarray(notes.head_result) != 300, 0, -1)[singles],
    }
    return {k: np.concatenate([rows[k], sl_rows[k], acc_rows[k]]) for k in rows}


def group(items: dict[str, np.ndarray], late: np.ndarray | None = None, weight: np.ndarray | None = None) -> IrtGroups:
    """Items (or groups) with the same kind, rounded difficulties and session flag added up into one group each;
    ``weight`` scales every row's counts."""
    count = len(items["kind"])
    if not count:
        return IrtGroups.from_columns({c: np.zeros(0) for c in IrtGroups.names()}, n=0)
    late = np.zeros(count) if late is None else np.asarray(late, dtype=float)
    weight = np.ones(count) if weight is None else np.asarray(weight, dtype=float)
    cols = ("b_aim", "b_flow", "b_tap", "b_stam", "b_read", "b_sl", "b_acc")
    rounded = np.column_stack(
        [np.where(np.isfinite(items[c]), np.round(items[c] / K.ROUND), -1e9) for c in cols]
        + [items["kind"].astype(float), late]
    )
    keys, inverse = np.unique(rounded, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    if "fail" in items:  # single items
        fail = items["fail"]
        n = np.ones(count)
        parts = [(fail == c).astype(float) for c in (0, 1, 2)]
    else:
        n, parts = items["n"], [items["f_a"], items["f_b"], items["f_t"]]

    def total(v: np.ndarray) -> np.ndarray:
        return np.bincount(inverse, weights=v * weight, minlength=len(keys))

    b = {c: np.where(keys[:, i] <= -1e8, np.nan, keys[:, i] * K.ROUND) for i, c in enumerate(cols)}
    return IrtGroups(
        kind=keys[:, len(cols)].astype(np.int64),
        late=keys[:, len(cols) + 1],
        n=total(n),
        f_a=total(parts[0]),
        f_b=total(parts[1]),
        f_t=total(parts[2]),
        **b,
    )


def group_table(notes: HitObjects, meta: ReplayMeta, timing_counts: bool = True) -> IrtGroups:
    """The :class:`IrtGroups` of one play's played notes."""
    return group(item_table(notes, meta, timing_counts))

"""Stamina: the tempo the player keeps over time, stream loads, and the stamina score."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from osu_coach.profile.domain.ranking import _n_replays, ranked_mean
from osu_coach.profile.domain.stats import _clip, _dur, _map_key

STAMINA_RUN = 16          # notes: a "long" stream
STAMINA_REACH = 10        # BPM above the clean stream speed that still counts as reachable (precision chart)
STAMINA_MAP_RUN = 8       # streams / bursts this long count towards a map's tapping load
STAMINA_KEPT = 0.9        # share of a stream's notes you must have pressed for: "your fingers kept going"
STAMINA_KEPT_ZERO = 0.6   # ... below this share a stream adds nothing; in between it counts partly
STAMINA_BPM_POWER = 3.0   # a note at 240 BPM loads (240/200)^3 = 1.73x a note at 200 BPM
STAMINA_STEADY_MIN = 0.3      # a stream that falls apart still counts 30% (you kept pressing)
STAMINA_OVERSTREAM = 0.95     # taps ≥ 5% faster than the notes = overstreaming: fine, never penalised
STAMINA_SLOW_FREE = 0.03      # steadiness of a long stream (info): the 2nd half may be 3% slower for free ...
STAMINA_SLOW_COST = 2.5       # ... then each 1% slower costs 2.5%
STAMINA_JITTER_FREE = 0.05    # the 2nd half's rhythm may get this much less even (spread / median) for free
STAMINA_JITTER_COST = 1.0
# stamina = the tempo you keep up for a given time (tempo-duration curve):
STAMINA_WINDOWS = (10, 30, 60, 120, 300)      # seconds
# 50 = this share of the stream speed typical for your level (stamina_ref_bpm), kept up for that long
# (set for the pp-style weighted average of all your maps, not your best few: a 6★ player's history and the 38
# reference plays of ~10★ players give about 0.52 / 0.45 / 0.40 / 0.37 and 0.71 / 0.61 / 0.52 / 0.42 at 10 s … 2 min)
STAMINA_WINDOW_SHARE = {10: 0.55, 30: 0.47, 60: 0.41, 120: 0.38, 300: 0.33}
STAMINA_MIN_MAPS = 2          # a duration counts once 2+ maps were played that long
STAMINA_BOOST = 1.05          # temporary +5% (review) until more players' data sets the yardstick
STAMINA_POINTS = 75.0         # points per doubling of the tempo (≈ 10 points for 10% faster)
PRESSED_REASONS = ("early", "late", "aim", "notelock")   # misses where a key was pressed


def stamina_ref_bpm(level: float | None) -> float:
    """Stream speed typical for a level (★): ~165 BPM at 3★, ~210 at 6★, ~255 at 9★."""
    if level is None or not np.isfinite(level):
        return 200.0
    return float(min(300.0, max(120.0, 120.0 + 15.0 * level)))


def _press_times(presses: pd.DataFrame | None, rates: dict) -> dict:
    """Real-time (ms, rate applied) press times per replay, sorted."""
    if presses is None or presses.empty or "time" not in presses:
        return {}
    out = {}
    for k, d in presses.groupby("replay_key", sort=False):
        out[k] = np.sort(d["time"].to_numpy(float)) / float(rates.get(k, 1.0) or 1.0)
    return out


def stream_rhythm(t: np.ndarray, start: float, end: float, bpm: float) -> dict | None:
    """How steady the taps of one stream were, from the key presses between its first and last note
    (real ms). Gaps are measured over two taps (left + right), so an uneven but regular alternation
    (e.g. a slightly faster left finger) is not "unsteady". Relative to the stream's note spacing:
    ``r1`` / ``r2`` = median tap gap in the 1st / 2nd half (1.0 = exactly with the notes, < 1 = faster:
    overstreaming), ``slow`` = how much slower the 2nd half got (speeding up / overstreaming = 0),
    ``jitter`` = how much less even the 2nd half got. ``steady`` (0.3–1) = the factor its load keeps."""
    gap = 15000.0 / bpm
    tt = t[(t >= start - 0.5 * gap) & (t <= end + 0.5 * gap)]
    if len(tt) < 12:
        return None
    g = (tt[2:] - tt[:-2]) / (2 * gap)
    h = len(g) // 2
    a, b = g[:h], g[h:]
    if len(a) < 4 or len(b) < 4:
        return None

    def spread(x):
        m = float(np.median(x))
        return float(1.4826 * np.median(np.abs(x - m)) / max(m, 1e-6))
    r1, r2 = float(np.median(a)), float(np.median(b))
    slow = max(0.0, r2 / max(r1, 1e-6) - 1.0)
    if r2 <= STAMINA_OVERSTREAM:      # still tapping faster than the notes at the end: overstreaming, fine
        slow = 0.0
    jitter = max(0.0, spread(b) - spread(a))
    steady = 1.0 - STAMINA_SLOW_COST * max(0.0, slow - STAMINA_SLOW_FREE) \
        - STAMINA_JITTER_COST * max(0.0, jitter - STAMINA_JITTER_FREE)
    return {"r1": r1, "r2": r2, "slow": slow, "jitter": jitter, "presses": int(len(tt)),
            "steady": float(min(1.0, max(STAMINA_STEADY_MIN, steady)))}


def stream_loads(P: pd.DataFrame, min_run: int = STAMINA_MAP_RUN, presses: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per stream / burst of ``min_run``+ notes in each play:

    * ``notes``, ``bpm``, ``start`` / ``end`` (real seconds into the map), ``completed`` (map finished);
    * ``kept``: share of its notes you pressed a key for — 100s, 50s and misses where you tapped (also too
      early: overstreaming) count; only no-tap / lost / never reached don't;
    * ``steady`` (0.3–1, from the key presses of streams of 16+ notes, 1 when unknown): did your taps slow
      down or get uneven in the second half? Overstreaming (tapping faster than the notes) is never a loss;
    * ``quality`` = kept part × steady: kept ≥ 90% counts fully, ≤ 60% not at all, linear in between;
    * ``load`` = notes × (BPM / 200)^3 × quality: equivalent notes at 200 BPM, so faster streams weigh much
      more; ``raw_load`` without the quality factor."""
    cols = ["replay_key", "run_id", "notes", "bpm", "start", "end", "kept", "steady", "slow", "overstream",
            "quality", "raw_load", "load", "completed"]
    if P is None or P.empty or "run_id" not in P:
        return pd.DataFrame(columns=cols)
    R = P[(P["run_id"] >= 0) & (P["run_len"] >= min_run)].dropna(subset=["stream_bpm"])
    if R.empty:
        return pd.DataFrame(columns=cols)
    reason = R["miss_reason"] if "miss_reason" in R else pd.Series(None, index=R.index, dtype=object)
    pressed = R["head_hit"].astype(bool) | reason.isin(PRESSED_REASONS)
    key = R["replay_key"] if "replay_key" in R else pd.Series("all", index=R.index)
    done = R["completed"] if "completed" in R else pd.Series(True, index=R.index)
    rate = R["rate"].astype(float).fillna(1.0) if "rate" in R else pd.Series(1.0, index=R.index)
    t = R["time"].astype(float) / rate if "time" in R else pd.Series(np.nan, index=R.index)
    D = pd.DataFrame({"replay_key": key, "run_id": R["run_id"], "pressed": pressed, "notes": R["run_len"],
                      "bpm": R["stream_bpm"].astype(float), "completed": done.astype(bool), "t": t,
                      "rate": rate})
    g = D.groupby(["replay_key", "run_id"], sort=False).agg(
        notes=("notes", "first"), bpm=("bpm", "first"), pressed=("pressed", "sum"), completed=("completed", "first"),
        t0=("t", "min"), t1=("t", "max"), rate=("rate", "first"))
    g = g.reset_index()
    g["kept"] = g["pressed"] / g["notes"].clip(lower=1)   # notes never reached (failed) count as not pressed
    g["start"], g["end"] = g["t0"] / 1000.0, g["t1"] / 1000.0
    times = _press_times(presses, dict(zip(g["replay_key"], g["rate"])))
    steady, slow, over = [], [], []
    for k, n, b, t0, t1 in zip(g["replay_key"], g["notes"], g["bpm"], g["t0"], g["t1"]):
        rh = stream_rhythm(times[k], t0, t1, b) if (n >= STAMINA_RUN and k in times and np.isfinite(t0)) else None
        steady.append(rh["steady"] if rh else 1.0)
        slow.append(rh["slow"] if rh else math.nan)
        over.append(bool(rh and rh["r1"] <= STAMINA_OVERSTREAM))
    g["steady"], g["slow"], g["overstream"] = steady, slow, over
    kept_part = ((g["kept"] - STAMINA_KEPT_ZERO) / (STAMINA_KEPT - STAMINA_KEPT_ZERO)).clip(0, 1)
    g["quality"] = kept_part * g["steady"]
    g["raw_load"] = g["notes"] * (g["bpm"] / 200.0) ** STAMINA_BPM_POWER
    g["load"] = g["raw_load"] * g["quality"]
    return g[cols]


def tempo_curve(P: pd.DataFrame, windows=STAMINA_WINDOWS) -> pd.DataFrame:
    """Stamina curve of every play: for each duration W (seconds), the fastest tempo you kept up for W seconds.

    Every note you tap (circles and slider heads, not spinners) counts if you pressed a key for it — 300s, 100s,
    50s and misses where you tapped (also too early: overstreaming); only notes you didn't press for (no tap,
    lost, not reached) don't. In every W-second stretch of the play: tempo = pressed notes per second as 1/4-note
    BPM (15 × notes per second, so a 220 BPM stream = 220), × the kept share (pressed 90%+ of the notes there =
    1, 60% or less = 0, linear between): when your fingers start to give in (undertapping), the tempo stops
    counting. ``bpm`` = the best stretch of the play. Only stretches inside what you played count (failed plays
    up to where they ended), and a play shorter than W has no value for W."""
    cols = ["replay_key", "map", "window", "bpm", "minutes"]
    if P is None or P.empty or "time" not in P:
        return pd.DataFrame(columns=cols)
    D = P[P["kind"] != "spinner"] if "kind" in P else P
    if D.empty:
        return pd.DataFrame(columns=cols)
    reason = D["miss_reason"] if "miss_reason" in D else pd.Series(None, index=D.index, dtype=object)
    pressed = (D["head_hit"].astype(bool) | reason.isin(PRESSED_REASONS)).to_numpy()
    rate = D["rate"].astype(float).fillna(1.0).to_numpy() if "rate" in D else np.ones(len(D))
    t_all = D["time"].astype(float).to_numpy() / rate / 1000.0
    keys = D["replay_key"].astype(str).to_numpy() if "replay_key" in D else np.full(len(D), "all")
    maps = _map_key(D).to_numpy()
    rows = []
    for k in pd.unique(keys):
        m = keys == k
        order = np.argsort(t_all[m])
        t, pr = t_all[m][order], pressed[m][order]
        if len(t) < 2:
            continue
        span = t[-1] - t[0]
        cp = np.concatenate([[0], np.cumsum(pr)])
        idx = np.arange(len(t))
        for W in windows:
            if span < W * 0.98:
                continue
            j = np.searchsorted(t, t + W, side="left")
            n = j - idx
            kept = cp[j] - cp[idx]
            share = np.where(n > 0, kept / np.maximum(n, 1), 0.0)
            q = np.clip((share - STAMINA_KEPT_ZERO) / (STAMINA_KEPT - STAMINA_KEPT_ZERO), 0, 1)
            bpm = np.where(t + W <= t[-1] + 0.02 * W, kept / W * 15.0 * q, 0.0)
            rows.append({"replay_key": k, "map": maps[m][0], "window": W, "bpm": float(bpm.max()),
                         "minutes": span / 60.0})
    return pd.DataFrame(rows, columns=cols)


def stamina_score(P: pd.DataFrame, tapping: dict | None = None, level: float | None = None,
                  presses: pd.DataFrame | None = None, n_total: int | None = None) -> dict:
    """Stamina: for how long you keep a high tempo without your fingers giving in — not how accurate you stay.

    osu!standard has no stamina skill of its own: the star rating's speed strain decays to 30% per second
    (osu!lazer ``Speed.cs``), so it only "remembers" the last second or two. This score uses
    :func:`tempo_curve`: the fastest tempo you kept up (still pressing 90%+ of the notes) for 10 s, 30 s, 1 min,
    2 min and 5 min. Overstreaming — tapping faster than the notes — never counts against you.

    * each duration: one value per map (your best play of it), ranked fastest first and weighted like osu!'s pp
      (:func:`ranked_mean`: 100%, then 1/N less per place, N = replays analysed); it counts once 2+ maps were
      played that long;
    * 50 = the tempo typical for your level for that long (``stamina_ref_bpm`` × ``STAMINA_WINDOW_SHARE``: the
      longer, the more pauses and slower parts any map has); 10% faster ≈ +10 points, twice as fast = +75;
    * the score = the average over the durations, so holding a tempo for minutes counts as much as a short
      burst of speed. Low-tempo marathons stay low (they don't show a high tempo), and death streams you can't
      keep up score low for the long durations.

    The steadiness numbers (did your taps slow down or get uneven in the second half of long streams) are shown
    for information. Difficulty weights are not used: the score asks what you *can* sustain."""
    ref_bpm = stamina_ref_bpm(level)
    out = {"score": None, "n": 0, "ref_bpm": ref_bpm, "curve": {}, "parts": {}, "maps": {}, "best": {},
           "ref_curve": {W: ref_bpm * STAMINA_WINDOW_SHARE[W] for W in STAMINA_WINDOWS},
           "streams_long": 0, "streams_kept": 0, "streams_slowed": 0, "streams_overstreamed": 0,
           "steadiness": math.nan, "best_stream": None, "longest_minutes": math.nan}
    C = tempo_curve(P)
    if len(C):
        out["longest_minutes"] = float(C["minutes"].max())
        out["n"] = int(C["map"].nunique())
    for W in STAMINA_WINDOWS:
        c = C[C["window"] == W]
        if c.empty:
            continue
        per_map = c.groupby("map")["bpm"].max().sort_values(ascending=False)
        out["maps"][W] = int(len(per_map))
        if len(per_map) < STAMINA_MIN_MAPS:
            continue
        v = ranked_mean(per_map.to_numpy(), n_total or _n_replays(P))
        out["curve"][W] = v
        out["best"][W] = float(per_map.iloc[0])
        out["parts"][W] = _clip(50 + STAMINA_POINTS * math.log2(max(v, 1e-6) / out["ref_curve"][W]))
    if out["parts"] and out["n"] >= 3:
        out["score"] = min(100.0, float(np.mean(list(out["parts"].values()))) * STAMINA_BOOST)
    # information: long streams and how steady your taps stayed in them
    L = stream_loads(P, presses=presses)
    long_all = L[L["notes"] >= STAMINA_RUN] if len(L) else L
    if len(long_all):
        measured = long_all[long_all["slow"].notna()]
        out.update(streams_long=int(len(long_all)), streams_kept=int((long_all["kept"] >= STAMINA_KEPT).sum()),
                   streams_slowed=int((measured["steady"] < 0.95).sum()),
                   streams_overstreamed=int(measured["overstream"].sum()),
                   steadiness=float(np.average(measured["steady"], weights=measured["raw_load"]))
                   if len(measured) else math.nan)
        kept = long_all[long_all["kept"] >= STAMINA_KEPT]
        if len(kept):
            b = kept.sort_values(["raw_load"], ascending=False).iloc[0]
            out["best_stream"] = {"notes": int(b["notes"]), "bpm": float(b["bpm"]), "steady": float(b["steady"])}
    bits = [f"{_dur(W)}: {v:.0f} BPM" for W, v in out["curve"].items()]
    if out["best_stream"]:
        bs = out["best_stream"]
        bits.append(f"hardest stream: {bs['notes']} notes at {bs['bpm']:.0f} BPM")
    if not math.isnan(out["steadiness"]):
        bits.append(f"steadiness {out['steadiness']:.0%}")
    out["detail"] = "; ".join(bits)
    return out

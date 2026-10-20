"""How ready each skill is for harder maps, and how consistently combo and accuracy hold.

Every skill gets a *level* in stars: the star rating of a typical map whose demand on that skill matches what the
player has shown. osu! rates a skill as the square root of its strain, so a map of ``target`` stars asks
``(target / level)²`` times the strain the skill handles: it feels ``(target / level)² − 1`` harder, and
``readiness = 1 − that`` (100% = comfortable, 0% = twice the strain: out of reach).

* aim, flow aim, speed: the hardest sections of that kind the player cleared, in osu!'s own section difficulty
  (``aim_eq`` / ``speed_eq`` turned into stars by the map's stars / skill rating), × the share of those notes hit;
* stamina: the hardest 30-second stretch of fast tapping, × the share of it kept up;
* accuracy, sliders, reading: a measured value (:func:`level_inputs`) against what maps at each star rating demand
  (the pool's curves, matched to how often the player uses DT and passed in): the timing spread against the 300
  window, the slider speed of the maps held (capped at the hardest pass + 0.5★: harder maps have faster, longer
  sliders in harder patterns), and note density × approach rate of the maps cleared, × the share of notes hit.

Section levels rank the plays like pp (best first, 0.95 decay) and divide by where such peaks sit on a typical map the
player played, so level 7 = handles what a typical 7★ map asks of this skill.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from osu_coach.profile.domain.sliders import slider_difficulty

AHEAD = 2.0  # targets more than this many stars above the comfort level are locked
STEP = 0.5  # the targets offered, in stars
MIN_PLAYS = 3
RANK_DECAY = 0.95
PEAK_QUANTILE = 0.95  # a play's peak = its hardest 5% of sections of that kind
MIN_SECTION_NOTES = 20
STAMINA_WINDOW = 30.0  # seconds
STAMINA_MIN_FAST = 20  # fast notes in a stretch
STAMINA_PLAY_FAST = 40  # fast notes in a play for it to test stamina at all
STAMINA_FAST_SHARE = 0.5  # a stretch counts fully when at least half of its notes are bursts / streams
SLIDER_TOP = 30
SLIDER_MIN = 10
SLIDER_CAP = 0.5  # the slider level stays within this many stars of the hardest pass
GREAT_Z = 1.959963984540054  # 95% of hits inside the 300 window
READ_MIN_NOTES = 30
ODD_RHYTHMS = ("1/3", "1/6", "1/8", "other")
LEVEL_RANGE = (1.0, 15.0)

# consistency: per star band with enough plays, combo and accuracy held across plays
BAND = 0.5  # stars
BAND_MIN_PLAYS = 10
ACC_BAD, ACC_GOOD = 0.93, 0.99  # accuracy scale: 93% → 0, 99% → 1
BEST_WEIGHT = 0.7  # the better of combo and accuracy carries the score; both good = top score
FULL_COMBO = 0.98  # share of the map's max combo (no misses) that counts as a full combo


def readiness(level: float | None, target: float) -> float | None:
    """1 − ((target / level)² − 1), clipped to 0–1; ``None`` without a level."""
    if level is None or not math.isfinite(level) or level <= 0:
        return None
    return float(np.clip(2 - (target / level) ** 2, 0, 1))


def reading_demand(density, odd_share, ar):
    """Busy-ness × approach rate: notes on screen (90th percentile) × (1 + share of odd rhythms), × (1 + a quarter
    per AR below 8 + half per AR above 10, with mods). Works on numbers and arrays."""
    return density * (1 + odd_share) * (1 + np.maximum(0, 8 - ar) / 4 + np.maximum(0, ar - 10) / 2)


def _ranked(values) -> float | None:
    """Best first, each next one counting 0.95× the one before (like pp)."""
    v = np.sort(np.asarray([x for x in values if x is not None and math.isfinite(x)], dtype=float))[::-1]
    if not len(v):
        return None
    return float(np.average(v, weights=np.power(RANK_DECAY, np.arange(len(v)))))


def _level(rows: list[tuple[float, float]]) -> dict:
    """rows = (value, value-or-peak per map star) per play → level in stars."""
    if len(rows) < MIN_PLAYS:
        return {"level": None, "plays": len(rows)}
    value = _ranked([r[0] for r in rows])
    per_star = float(np.median([r[1] for r in rows]))
    if value is None or per_star <= 0:
        return {"level": None, "plays": len(rows)}
    return {"level": float(np.clip(value / per_star, *LEVEL_RANGE)), "plays": len(rows)}


def _stars_per(metas: pd.DataFrame, rating: str) -> pd.Series:
    """Map stars / skill rating per replay: turns rosu-pp's section values (skill rating units) into stars."""
    m = metas.drop_duplicates("key").set_index("key")
    if rating not in m or "stars" not in m:
        return pd.Series(dtype=float)
    r = pd.to_numeric(m[rating], errors="coerce")
    return pd.to_numeric(m["stars"], errors="coerce") / r.where(r > 0)


def _peaks(P: pd.DataFrame, mask: pd.Series, col: str, stars: pd.Series) -> dict:
    rows = []
    for key, d in P[mask].groupby("replay_key", sort=False):
        v = d[col].dropna()
        s = stars.get(key)
        if len(v) < MIN_SECTION_NOTES or s is None or not s > 0:
            continue
        top = d.loc[v.index[v >= v.quantile(PEAK_QUANTILE)]]
        peak = float(top[col].mean())
        rows.append((peak * float(top["head_hit"].astype(bool).mean()), peak / s))
    return _level(rows)


def _stamina(P: pd.DataFrame, stars: pd.Series) -> dict:
    rows = []
    for key, d in P.groupby("replay_key", sort=False):
        s = stars.get(key)
        d = d.sort_values("t")
        tt = d["t"].to_numpy(float)
        if s is None or not s > 0 or (d["run_len"] >= 3).sum() < STAMINA_PLAY_FAST or tt[-1] - tt[0] < STAMINA_WINDOW:
            continue
        lvl = d["speed_s"].to_numpy(float)
        fast = (d["run_len"] >= 3).to_numpy() & np.isfinite(lvl)
        kept = d["head_hit"].astype(bool).to_numpy()
        cum = lambda x: np.concatenate([[0.0], np.cumsum(x)])  # noqa: E731
        c_fast, c_lvl, c_kept = cum(fast), cum(np.where(fast, lvl, 0.0)), cum(fast & kept)
        i = np.arange(len(d))
        j = np.searchsorted(tt, tt + STAMINA_WINDOW)
        n_fast = c_fast[j] - c_fast[i]
        ok = n_fast >= STAMINA_MIN_FAST
        if not ok.any():
            continue
        nf = n_fast[ok]
        mean_lvl = (c_lvl[j] - c_lvl[i])[ok] / nf
        kept_share = (c_kept[j] - c_kept[i])[ok] / nf
        busy = np.minimum(1.0, nf / (j - i)[ok] / STAMINA_FAST_SHARE)
        best = float((mean_lvl * kept_share * busy).max())
        rows.append((best, best / s))
    return _level(rows)


def section_levels(P: pd.DataFrame, metas: pd.DataFrame) -> dict[str, dict]:
    """Aim, flow aim, speed and stamina levels (stars) from the sections the player cleared."""
    out = {k: {"level": None, "plays": 0} for k in ("aim", "flow_aim", "speed", "stamina")}
    need = {"replay_key", "aim_eq", "speed_eq", "head_hit", "pattern", "run_len", "run_pos", "spaced_stream", "time"}
    if P is None or P.empty or not need <= set(P.columns):
        return out
    P = P[P["kind"] != "spinner"] if "kind" in P else P
    aim_stars, speed_stars = _stars_per(metas, "aim"), _stars_per(metas, "speed")
    stars = metas.drop_duplicates("key").set_index("key")["stars"].astype(float)
    P = P.assign(
        aim_s=P["aim_eq"].astype(float) * P["replay_key"].map(aim_stars),
        speed_s=P["speed_eq"].astype(float) * P["replay_key"].map(speed_stars),
        t=P["time"].astype(float) / (P["rate"].astype(float) if "rate" in P else 1.0) / 1000,
    )
    jumps = P["pattern"].isin(["jump", "spaced"]) & (P["run_len"] < 3)
    flow = P["spaced_stream"].astype(bool) & (P["run_pos"] > 0)
    out["aim"] = _peaks(P, jumps, "aim_s", stars)
    out["flow_aim"] = _peaks(P, flow, "aim_s", stars)
    out["speed"] = _peaks(P, P["run_len"] >= 3, "speed_s", stars)
    out["stamina"] = _stamina(P, stars)
    return out


def _timing_spread(rate: float, windows: list) -> float | None:
    """The hit-timing spread (ms, one standard deviation) that gives this non-300 rate on these 300 windows."""
    w = [(float(a), float(b)) for a, b in windows or [] if b > 0]
    if not w or rate is None or not 0 < rate < 1:
        return None
    windows_ms, weights = np.array([a for a, _ in w]), np.array([b for _, b in w])

    def non_300(sigma: float) -> float:
        return float(np.average([math.erfc(x / (math.sqrt(2) * sigma)) for x in windows_ms], weights=weights))

    lo, hi = 0.1, 200.0
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if non_300(mid) < rate else (lo, mid)
    return (lo + hi) / 2


def level_inputs(P: pd.DataFrame, metas: pd.DataFrame, ratings: dict) -> dict:
    """What the pool-based levels need: the player's timing spread, slider speed held, reading demand cleared, their DT
    share and hardest pass. ``ratings`` = the comfort-relative ratings (``experimental_skills``)."""
    m = metas.drop_duplicates("key")
    rate = pd.to_numeric(m.get("rate", pd.Series(1.0, index=m.index)), errors="coerce").fillna(1.0)
    done = m["completed"].astype(bool) if "completed" in m else pd.Series(True, index=m.index)
    stars = pd.to_numeric(m["stars"], errors="coerce") if "stars" in m else pd.Series(np.nan, index=m.index)
    out = {
        "dt_share": float((rate > 1.01).mean()) if len(m) else 0.0,
        "hardest_pass": float(stars[done].max()) if done.any() and stars[done].notna().any() else None,
        "timing_spread": None,
        "slider_speed": None,
        "reading": None,
        "reading_plays": 0,
    }
    acc = ratings.get("accuracy") or {}
    out["timing_spread"] = _timing_spread(acc.get("measured"), acc.get("od_windows"))
    if P is None or P.empty:
        return out
    P = P[P["kind"] != "spinner"] if "kind" in P else P

    # sliders: the measured slider demand (comfort-relative rating) in slider speed, by how the hardest 30 sliders
    # relate to the median slider speed on the player's own maps
    held = P[(P["kind"] == "slider") & P["head_hit"].astype(bool)] if "kind" in P else P.iloc[0:0]
    ratios = []
    for _, d in held.groupby("replay_key", sort=False):
        if len(d) < SLIDER_MIN:
            continue
        speed = d["slider_vel_real"].astype(float) * 1000 / (2 * d["radius"].astype(float).clip(lower=1.0))
        top = float(slider_difficulty(d).nlargest(SLIDER_TOP).mean())
        if speed.median() > 0:
            ratios.append(top / float(speed.median()))
    measured = (ratings.get("sliders") or {}).get("measured")
    if ratios and measured is not None and math.isfinite(measured):
        out["slider_speed"] = float(measured) / float(np.median(ratios))

    # reading: busy-ness × approach rate of every completed play, × the share of its notes hit
    ar = m.set_index("key")["ar"].astype(float) if "ar" in m else pd.Series(dtype=float)
    ok = P["completed"].astype(bool) if "completed" in P else pd.Series(True, index=P.index)
    values = []
    for key, d in P[ok].groupby("replay_key", sort=False):
        if len(d) < READ_MIN_NOTES or key not in ar or not math.isfinite(ar[key]) or "density" not in d:
            continue
        rhythm = d["rhythm"].dropna() if "rhythm" in d else pd.Series(dtype=object)
        rhythm = rhythm[rhythm != "break"]
        odd = float(rhythm.isin(ODD_RHYTHMS).mean()) if len(rhythm) else 0.0
        demand = reading_demand(float(d["density"].quantile(0.9)), odd, float(ar[key]))
        values.append(demand * float(d["head_hit"].astype(bool).mean()))
    out["reading"] = _ranked(values) if len(values) >= MIN_PLAYS else None
    out["reading_plays"] = len(values)
    return out


def curve_level(value: float | None, curve) -> float | None:
    """The star rating at which a demand curve (stars, values, map counts) reaches ``value``: a power law fitted
    through the curve (weighted by map count), so a flat stretch can't throw the level by several stars."""
    if value is None or not math.isfinite(value) or value <= 0 or curve is None:
        return None
    s, v, n = (np.asarray(x, dtype=float) for x in curve)
    keep = (s > 0) & (v > 0) & (n > 0)
    if keep.sum() < 3:
        return None
    slope, intercept = np.polyfit(np.log(s[keep]), np.log(v[keep]), 1, w=np.sqrt(n[keep]))
    if abs(slope) < 1e-6:
        return None
    return float(np.clip(math.exp((math.log(value) - intercept) / slope), *LEVEL_RANGE))


def pool_levels(inputs: dict, curves: dict) -> dict[str, dict]:
    """Accuracy, sliders and reading levels from :func:`level_inputs` and the pool's demand curves."""
    sigma = inputs.get("timing_spread")
    accuracy = curve_level(GREAT_Z * sigma, curves.get("window")) if sigma else None
    raw = curve_level(inputs.get("slider_speed"), curves.get("slider_speed"))
    cap = inputs.get("hardest_pass")
    sliders = min(raw, cap + SLIDER_CAP) if raw is not None and cap is not None else raw
    return {
        "accuracy": {"level": accuracy, "timing_spread": sigma},
        "sliders": {
            "level": sliders,
            "uncapped": raw,
            "capped": raw is not None and sliders is not None and sliders < raw,
        },
        "reading": {
            "level": curve_level(inputs.get("reading"), curves.get("reading")),
            "plays": inputs.get("reading_plays", 0),
        },
    }


# ------------------------------------------------------------------ consistency
def _held(x: np.ndarray) -> float:
    """Usual level minus how much it swings between plays (one standard deviation), clipped to 0–1."""
    return float(np.clip(x.mean() - x.std(), 0, 1))


def band_consistency(combo: float, accuracy: float) -> float:
    """0–100: the better of combo and accuracy held carries the score, both good = top score, both bad = low."""
    return 100 * (BEST_WEIGHT * max(combo, accuracy) + (1 - BEST_WEIGHT) * min(combo, accuracy))


def consistency_bands(metas: pd.DataFrame) -> list[dict]:
    """Per 0.5★ band (star rating with mods): how consistently combo and accuracy hold across the plays there.
    Scored only with 10+ plays in the band."""
    need = {"stars", "max_combo", "map_max_combo", "accuracy"}
    if metas is None or metas.empty or not need <= set(metas.columns):
        return []
    m = metas.drop_duplicates("key") if "key" in metas else metas
    m = m.assign(
        stars=pd.to_numeric(m["stars"], errors="coerce"),
        accuracy=pd.to_numeric(m["accuracy"], errors="coerce"),
        top=pd.to_numeric(m["map_max_combo"], errors="coerce"),
    )
    m = m[m["stars"].notna() & m["accuracy"].notna() & (m["top"] > 0)]
    if m.empty:
        return []
    combo = (pd.to_numeric(m["max_combo"], errors="coerce").fillna(0) / m["top"]).clip(0, 1)
    misses = pd.to_numeric(m["nmiss"], errors="coerce").fillna(0) if "nmiss" in m else pd.Series(0, index=m.index)
    m = m.assign(
        combo=combo,
        acc_scale=((m["accuracy"] - ACC_BAD) / (ACC_GOOD - ACC_BAD)).clip(0, 1),
        full=(combo >= FULL_COMBO) & (misses == 0),
        band=np.floor(m["stars"] / BAND) * BAND,
    )
    bands = []
    for low, d in m.groupby("band", sort=True):
        enough = len(d) >= BAND_MIN_PLAYS
        combo_held = _held(d["combo"].to_numpy(float)) if enough else None
        acc_held = _held(d["acc_scale"].to_numpy(float)) if enough else None
        bands.append(
            {
                "low": float(low),
                "high": float(low) + BAND,
                "plays": len(d),
                "combo": combo_held,
                "accuracy": acc_held,
                "score": band_consistency(combo_held, acc_held) if enough else None,
                "full_combo_share": float(d["full"].mean()),
                "mean_accuracy": float(d["accuracy"].mean()),
            }
        )
    return bands

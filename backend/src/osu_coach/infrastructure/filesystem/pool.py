"""Practice map pool: per-difficulty pattern statistics + skill scores,
map suggestions and staged "improve a skill" playlists.

The bundled pool (``data/pool.json.gz``) holds ~5,000 popular ranked osu!standard
difficulties, 9 in 10 of them between 2★ and 8★ (most-played per 0.25★ step, from the
12,000 most-played ranked sets), each analysed
with the same pattern detector used on the player's replays plus osu!'s own
difficulty model (rosu-pp). Rebuild with ``dev_tools/build_pool.py``.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from osu_coach.domain import difficulty
from osu_coach.domain.beatmap import PlayableBeatmap
from osu_coach.infrastructure.filesystem.beatmap import parse_beatmap_bytes
from osu_coach.domain.features import object_features

POOL_PATH = Path(__file__).parent.parent / "data" / "pool.json.gz"
QUADRANTS = ["top-left", "top-right", "bottom-left", "bottom-right"]
SKILLS = ["aim", "flow_aim", "speed", "stamina", "accuracy", "sliders", "reading", "consistency"]

SKILL_INFO = {
    "aim": {"label": "Jump aim", "offset": 0.0, "focus": "landing on the centre of each circle"},
    "flow_aim": {"label": "Flow aim (spaced streams)", "offset": 0.0, "focus": "smooth, continuous cursor movement"},
    "speed": {"label": "Tapping speed (bursts/streams)", "offset": 0.0, "focus": "even, strictly alternating taps"},
    "stamina": {"label": "Stamina", "offset": -0.3, "focus": "keeping the tempo until the stream ends"},
    "accuracy": {"label": "Accuracy (timing)", "offset": -0.7, "focus": "300s — tap exactly with the music"},
    "sliders": {"label": "Slider control", "offset": -0.5, "focus": "following the ball until the slider ends"},
    "reading": {"label": "Reading (dense parts / AR)", "offset": -0.3, "focus": "looking ahead at the next notes"},
    "consistency": {"label": "Consistency", "offset": -0.5, "focus": "staying calm after a mistake"},
    "quadrant": {"label": "Weak quadrant", "offset": -0.2, "focus": "committing to the full movement into the corner"},
    "general": {"label": "Level up", "offset": 0.3, "focus": "passing slightly harder maps"},
}
STAGES = [("Warm-up", -0.6), ("Core", 0.0), ("Push", 0.5)]


def _f(v, default=math.nan) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(v) or math.isinf(v) else v


def _c(v, lo: float, hi: float) -> float:
    """Clamp-normalise v from [lo, hi] to [0, 1]; NaN/None -> 0."""
    v = _f(v)
    if math.isnan(v):
        return 0.0
    return float(min(1.0, max(0.0, (v - lo) / (hi - lo))))


# ------------------------------------------------------------------ per-map statistics
def map_stats(osu_bytes: bytes) -> dict | None:
    """Pattern + difficulty statistics of one .osu file (NoMod)."""
    try:
        bm = parse_beatmap_bytes(osu_bytes)
    except Exception:  # noqa: BLE001 - broken files are skipped
        return None
    if bm.mode != 0 or len(bm.objects) < 30:
        return None
    pb = PlayableBeatmap(bm, 0)
    f = object_features(pb)
    ns = f[f["kind"] != "spinner"]
    if ns.empty:
        return None
    pat = ns["pattern"]
    jumps = ns[pat.isin(["jump", "spaced"])]
    streams = ns[ns["run_len"] >= 9]
    bursts = ns[(ns["run_len"] >= 3) & (ns["run_len"] < 9)]
    sliders = ns[ns["kind"] == "slider"]
    runs = ns[ns["run_id"] >= 0]
    run_sizes = runs.groupby("run_id")["run_len"].first() if len(runs) else pd.Series(dtype=float)
    rhythm = ns["rhythm"].dropna()
    rhythm = rhythm[rhythm != "break"]
    s = {
        "md5": hashlib.md5(osu_bytes).hexdigest(),
        "title": bm.title, "artist": bm.artist, "version": bm.version_name, "creator": bm.creator,
        "beatmap_id": bm.beatmap_id, "beatmapset_id": bm.beatmapset_id,
        "cs": bm.cs, "ar": bm.ar, "od": bm.od, "hp": bm.hp,
        "bpm": bm.main_bpm(), "drain_length": bm.drain_seconds, "n_objects": int(len(f)),
        "circle_share": float((ns["kind"] == "circle").mean()),
        "slider_share": float((ns["kind"] == "slider").mean()),
        "stream_share": float((pat == "stream").mean()),
        "burst_share": float((pat == "burst").mean()),
        "jump_share": float((pat == "jump").mean()),
        "spaced_share": float((pat == "spaced").mean()),
        "spaced_stream_share": float(ns["spaced_stream"].mean()),
        "stream_bpm": _f(streams["stream_bpm"].median()) if len(streams) else math.nan,
        "burst_bpm": _f(bursts["stream_bpm"].median()) if len(bursts) else math.nan,
        "max_run": int(ns["run_len"].max()),
        "long_runs": int((run_sizes >= 16).sum()),
        "stream_notes": int(len(streams)),
        "n_jumps": int(len(jumps)),
        "jump_dist": _f(jumps["dist_norm"].median()) if len(jumps) else math.nan,
        "jump_velocity": _f(jumps["velocity_real"].median()) if len(jumps) else math.nan,
        "sharp_share": _f((jumps["angle"] < 60).mean()) if jumps["angle"].notna().any() else math.nan,
        "slider_velocity": _f(sliders["slider_vel_real"].median()) if len(sliders) else math.nan,
        "reverse_share": float((sliders["slider_spans"] > 1).mean()) if len(sliders) else 0.0,
        "density_p90": _f(ns["density"].quantile(0.9)),
        "density_median": _f(ns["density"].median()),
        "odd_rhythm_share": float(rhythm.isin(["1/3", "1/6", "1/8", "other"]).mean()) if len(rhythm) else 0.0,
    }
    for q in QUADRANTS:
        s["q_" + q.replace("-", "_")] = float((jumps["quadrant"] == q).mean()) if len(jumps) else 0.0
    a = difficulty.attributes(osu_bytes, 0)
    s.update({"stars": a.get("stars", math.nan), "aim": a.get("aim", math.nan), "speed": a.get("speed", math.nan),
              "slider_factor": a.get("slider_factor", 1.0), "max_combo": a.get("max_combo", math.nan),
              "speed_note_count": a.get("speed_note_count", math.nan)})
    s["stars_dt"] = difficulty.attributes(osu_bytes, 64).get("stars", math.nan)
    s["evenness"] = _evenness(osu_bytes)
    s.update(skill_scores(s))
    return s


def _evenness(osu_bytes: bytes) -> float:
    """Median / peak section difficulty in star units (1 = equally hard throughout)."""
    st = difficulty.strains(osu_bytes, 0)
    if not st or not st.get("aim"):
        return math.nan
    aim = np.sqrt(10 * np.asarray(st["aim"], dtype=float))
    speed = np.sqrt(10 * np.asarray(st["speed"] or [0.0] * len(aim), dtype=float))
    n = min(len(aim), len(speed))
    comb = np.maximum(aim[:n], speed[:n])
    comb = comb[comb > 0]
    return float(np.median(comb) / comb.max()) if len(comb) else math.nan


def skill_scores(s: dict) -> dict:
    """How useful a map is for training each skill, 0..1 (heuristics on pattern stats)."""
    aim, speed = _f(s.get("aim"), 0.0), _f(s.get("speed"), 0.0)
    aim_ratio = aim / (aim + speed) if aim + speed > 0 else 0.5
    jumpy = _f(s.get("jump_share"), 0) + 0.5 * _f(s.get("spaced_share"), 0)
    tappy = _f(s.get("stream_share"), 0) + 0.6 * _f(s.get("burst_share"), 0)
    return {
        "s_aim": 0.6 * _c(jumpy, 0.05, 0.40) + 0.4 * _c(aim_ratio, 0.45, 0.60),
        "s_flow_aim": _c(s.get("spaced_stream_share"), 0.02, 0.20),
        "s_speed": 0.7 * _c(tappy, 0.05, 0.40) + 0.3 * _c(1 - aim_ratio, 0.40, 0.55),
        "s_stamina": 0.5 * _c(s.get("stream_notes"), 50, 400) + 0.3 * _c(s.get("max_run"), 12, 48)
                     + 0.2 * _c(s.get("drain_length"), 90, 300),
        "s_accuracy": 0.5 * _c(s.get("od"), 6.5, 9.5) + 0.3 * _c(s.get("circle_share"), 0.3, 0.8)
                      + 0.2 * (1 - _c(jumpy, 0.1, 0.5)),
        "s_sliders": 0.45 * _c(s.get("slider_share"), 0.25, 0.65) + 0.35 * _c(1 - _f(s.get("slider_factor"), 1.0), 0, 0.08)
                     + 0.2 * _c(s.get("reverse_share"), 0.05, 0.35),
        "s_reading": 0.6 * _c(s.get("density_p90"), 4, 10) + 0.4 * _c(s.get("odd_rhythm_share"), 0.0, 0.15),
        "s_consistency": 0.5 * _c(s.get("drain_length"), 90, 270) + 0.5 * _c(s.get("evenness"), 0.3, 0.7),
    }


# ------------------------------------------------------------------ pool loading
@lru_cache(maxsize=2)
def _load_cached(path: str, mtime: float) -> pd.DataFrame:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        rows = json.load(fh)
    df = pd.DataFrame(rows)
    for col in df.columns:
        if df[col].dtype == object and col not in ("md5", "title", "artist", "version", "creator", "status",
                                                    "ranked_date"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_pool(path: Path | str | None = None) -> pd.DataFrame:
    p = Path(path or POOL_PATH)
    if not p.exists():
        return pd.DataFrame()
    return _load_cached(str(p), p.stat().st_mtime).copy()


def save_pool(rows: list[dict], path: Path | str = POOL_PATH) -> Path:
    def clean(v):
        if isinstance(v, (np.floating, float)):
            v = float(v)
            return None if math.isnan(v) or math.isinf(v) else round(v, 4)
        if isinstance(v, np.integer):
            return int(v)
        return v
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump([{k: clean(v) for k, v in r.items()} for r in rows], fh, separators=(",", ":"))
    return p


# ------------------------------------------------------------------ targets & suggestions
@dataclass
class Targets:
    comfort: float = 2.5                    # star rating the player handles comfortably
    stream_bpm: float | None = None         # stream speed to train at (1/4 notes)
    quadrant: str | None = None             # weakest quadrant (if significant)
    ar_range: tuple[float, float] | None = None
    played: frozenset = field(default_factory=frozenset)


def targets_from_profile(p) -> Targets:
    lv = getattr(p, "levels", {}) or {}
    comfort = _f(lv.get("level_stars", lv.get("comfort_stars")))   # detected (or chosen) level, else comfort
    if math.isnan(comfort):
        comfort = _f(lv.get("comfort_stars"))
    if math.isnan(comfort):
        comfort = _f((getattr(p, "overview", {}) or {}).get("avg_stars")) - 0.5
    if math.isnan(comfort):
        comfort = 2.5
    comfort = float(min(8.0, max(1.0, comfort)))
    tap = getattr(p, "tapping", {}) or {}
    bpm = tap.get("comfort_bpm")
    if bpm is None and tap.get("limit_bpm"):
        bpm = tap["limit_bpm"] - 20
    stream_bpm = float(bpm) + 10 if bpm else None
    wq = getattr(p, "worst_quadrant", None)
    quadrant = wq["quadrant"] if wq and wq.get("significant") else None
    rd = getattr(p, "reading", {}) or {}
    # difficulty-adjusted (observed / expected misses) when available, raw miss rates otherwise
    adjusted = not math.isnan(_f(rd.get("mid_ar_ratio")))
    key = "_ratio" if adjusted else "_miss_rate"
    hi, mid, lo = (_f(rd.get(k + key)) for k in ("high_ar", "mid_ar", "low_ar"))
    factor = 1.3 if adjusted else 1.5
    ar_range = None
    if not math.isnan(hi) and not math.isnan(mid) and mid > 0 and hi >= factor * mid:
        ar_range = (9.0, 9.7)
    elif not math.isnan(lo) and not math.isnan(mid) and mid > 0 and lo >= factor * mid:
        ar_range = (5.0, 8.0)
    reps = getattr(p, "replays", None)
    played = frozenset(reps["beatmap_md5"].dropna().astype(str)) if reps is not None and len(reps) else frozenset()
    return Targets(comfort=comfort, stream_bpm=stream_bpm, quadrant=quadrant, ar_range=ar_range, played=played)


def _skill_column(pool: pd.DataFrame, skill: str, t: Targets) -> pd.Series:
    if skill == "quadrant" and t.quadrant:
        q = pool["q_" + t.quadrant.replace("-", "_")]
        jumpy = pool["jump_share"] + 0.5 * pool["spaced_share"]
        ok = pool["n_jumps"] >= 40
        return (0.55 * ((q - 0.25) / 0.2).clip(0, 1) + 0.45 * ((jumpy - 0.05) / 0.3).clip(0, 1)).where(ok, 0.0)
    if skill == "general":
        return pd.Series(0.5, index=pool.index)
    return pool.get("s_" + skill, pd.Series(0.0, index=pool.index)).fillna(0.0)


def _bpm_fit(pool: pd.DataFrame, target: float | None) -> pd.Series:
    if not target:
        return pd.Series(0.5, index=pool.index)
    bpm = pool["stream_bpm"].fillna(pool["burst_bpm"])
    return (1 - ((bpm - target).abs() / 30).clip(0, 1)).fillna(0.0)


def _title_key(title) -> str:
    return re.sub(r"\s*[\(\[].*?[\)\]]", "", str(title or "").lower()).strip()


def suggest(pool: pd.DataFrame, skill: str, targets: Targets, n: int = 10, offset: float | None = None,
            width: float = 0.5, exclude: set | frozenset = frozenset(), min_skill: float = 0.35,
            exclude_titles: set | frozenset = frozenset()) -> pd.DataFrame:
    """Best practice maps for a skill around the player's level (easiest first).

    Candidates come from a star window around the target (widened until there is
    enough choice). The skill threshold is relative inside that window, so a skill
    with little material at the player's level (streams at 2★) still gets the best
    maps that exist there instead of nothing."""
    if pool is None or pool.empty:
        return pd.DataFrame()
    info = SKILL_INFO.get(skill, SKILL_INFO["general"])
    target = float(min(8.3, max(1.0, targets.comfort + (info["offset"] if offset is None else offset))))
    blocked = set(exclude) | set(targets.played)
    base = pool[~pool["md5"].isin(blocked)].copy()
    if exclude_titles:
        base = base[~base["title"].map(_title_key).isin(exclude_titles)]
    if base.empty:
        return base
    base["skill_fit"] = _skill_column(base, skill, targets)
    if skill == "accuracy":   # timing practice needs tight hit windows *for the player's level*
        od_min = min(8.5, 3.0 + targets.comfort)
        base["skill_fit"] = 0.5 * base["skill_fit"] + 0.5 * ((base["od"] - (od_min - 2.5)) / 2.5).clip(0, 1).fillna(0)
    if skill == "reading" and targets.ar_range:
        lo, hi = targets.ar_range
        in_ar = base[(base["ar"] >= lo) & (base["ar"] <= hi)]
        if len(in_ar) >= 3 * n:
            base = in_ar
    tgt_bpm = None
    if skill in ("speed", "stamina"):
        has = base["stream_bpm"].notna() | base["burst_bpm"].notna()
        if has.sum() >= 3 * n:
            base = base[has]
        if targets.stream_bpm:
            tgt_bpm = targets.stream_bpm - (10 if skill == "stamina" else 0)
    base["bpm_fit"] = _bpm_fit(base, tgt_bpm) if tgt_bpm else 0.5
    base["star_dist"] = (base["stars"] - target).abs()
    w = width
    win = base.iloc[0:0]
    for _ in range(4):
        win = base[base["star_dist"] <= w]
        if win["beatmapset_id"].nunique() >= 3 * n:
            break
        w *= 1.5
    if win["beatmapset_id"].nunique() < n:   # thin region of the pool: take the closest maps
        win = base.nsmallest(max(6 * n, 60), "star_dist")
        w = max(w, float(win["star_dist"].max()) or w)
    if win.empty:
        return win
    thr = min(min_skill, float(win["skill_fit"].quantile(0.6)))
    cand = win.copy()
    pop = np.log1p(cand["playcount"].fillna(0).clip(lower=0))
    cand["popularity"] = pop.rank(pct=True)
    cand["star_fit"] = 1 - (cand["star_dist"] / w).clip(0, 1)
    bpm_w = 0.3 if tgt_bpm else 0.0
    cand["score"] = (0.55 * cand["skill_fit"] + 0.25 * cand["star_fit"] + 0.20 * cand["popularity"]
                     + bpm_w * cand["bpm_fit"])
    # maps above the skill threshold first; the rest only fill up a thin region
    cand["ok"] = cand["skill_fit"] >= thr
    cand = cand.sort_values(["ok", "score"], ascending=False).drop_duplicates("beatmapset_id")
    picked, per_creator, titles = [], {}, set()
    for idx, row in cand.iterrows():
        c, tk = str(row.get("creator", "")), _title_key(row.get("title"))
        if per_creator.get(c, 0) >= 2 or tk in titles:
            continue
        per_creator[c] = per_creator.get(c, 0) + 1
        titles.add(tk)
        picked.append(idx)
        if len(picked) >= n:
            break
    out = cand.loc[picked].sort_values("stars").copy()
    out["skill"] = skill
    out["why"] = [why(r, skill, targets) for _, r in out.iterrows()]
    out["url"] = [map_url(r) for _, r in out.iterrows()]
    return out.reset_index(drop=True)


def stream_length_maps(pool: pd.DataFrame, targets: Targets, min_run: int, max_run: int, n: int = 6,
                       offset: float = -0.3) -> pd.DataFrame:
    """Maps whose longest stream is ``min_run``–``max_run`` notes, at a stream speed the player can tap
    (``targets.stream_bpm``) and around his level: for practising streams of exactly that length."""
    if pool is None or pool.empty or "max_run" not in pool:
        return pd.DataFrame()
    sub = pool[(pool["max_run"] >= min_run) & (pool["max_run"] <= max_run)]
    if sub.empty:
        return sub
    out = suggest(sub, "stamina", targets, n=n, offset=offset, min_skill=0.0)
    if not out.empty:
        out["why"] = [f"longest stream {int(r['max_run'])} notes at ~{_f(r.get('stream_bpm'), _f(r.get('burst_bpm'), 0)):.0f}"
                      f" BPM (1/4)" for _, r in out.iterrows()]
    return out


PLAYLIST_COLUMNS = ["stage", "goal", "stars", "artist", "title", "version", "creator", "why", "url", "md5",
                    "beatmap_id", "beatmapset_id", "bpm", "ar", "od", "drain_length"]


def build_playlist(pool: pd.DataFrame, skill: str, targets: Targets, n: int = 15) -> pd.DataFrame:
    """Three stages (warm-up / core / push) of practice maps for one skill."""
    base_offset = SKILL_INFO.get(skill, SKILL_INFO["general"])["offset"]
    deltas = (-0.3, 0.0, 0.3) if skill == "accuracy" else tuple(d for _, d in STAGES)
    per = [n // 3, n - 2 * (n // 3), n // 3]
    parts, used, titles = [], set(), set()
    for (stage, _), delta, k in zip(STAGES, deltas, per):
        if k <= 0:
            continue
        part = suggest(pool, skill, targets, n=k, offset=base_offset + delta, width=0.3, exclude=used,
                       exclude_titles=titles)
        if part.empty:
            continue
        used |= set(pool.loc[pool["beatmapset_id"].isin(part["beatmapset_id"]), "md5"])
        titles |= {_title_key(t) for t in part["title"]}
        part.insert(0, "stage", stage)
        part.insert(1, "goal", [goal(stage, skill, targets) for _ in range(len(part))])
        parts.append(part)
    if not parts:
        return pd.DataFrame(columns=PLAYLIST_COLUMNS)
    return pd.concat(parts, ignore_index=True)


def goal(stage: str, skill: str, t: Targets) -> str:
    if skill == "accuracy":
        return {"Warm-up": "98%+ accuracy", "Core": "96%+ accuracy", "Push": "94%+ accuracy"}[stage]
    focus = SKILL_INFO.get(skill, SKILL_INFO["general"])["focus"]
    if skill == "quadrant" and t.quadrant:
        focus = f"committing to the full movement into the {t.quadrant} corner"
    return {"Warm-up": f"Full combo — focus on {focus}",
            "Core": "Under 5 misses, then go for the full combo",
            "Push": "Pass it, then retry the hardest section"}[stage]


def why(r, skill: str, t: Targets) -> str:
    g = lambda k, d=math.nan: _f(r.get(k), d)  # noqa: E731
    if skill == "aim":
        return f"{g('jump_share') + g('spaced_share'):.0%} jumps, ~{g('jump_dist', 0):.1f} circles apart"
    if skill == "flow_aim":
        return f"{g('spaced_stream_share'):.0%} spaced streams"
    if skill in ("speed", "stamina"):
        bpm = g("stream_bpm")
        bpm = g("burst_bpm") if math.isnan(bpm) else bpm
        run = int(g("max_run", 0))
        kind = "streams" if run >= 9 else "bursts"
        if skill == "stamina":
            long_runs = int(g("long_runs", 0))
            extra = f", {long_runs} streams of 16+ notes" if long_runs else f", longest {run} notes"
            return f"{kind} at ~{bpm:.0f} BPM (1/4){extra}"
        return f"{kind} at ~{bpm:.0f} BPM (1/4), longest {run} notes"
    if skill == "accuracy":
        return f"OD {g('od'):g}, {g('circle_share'):.0%} circles"
    if skill == "sliders":
        tricky = ", tricky slider paths" if g("slider_factor", 1) < 0.97 else ""
        return f"{g('slider_share'):.0%} sliders, {g('reverse_share'):.0%} with repeats{tricky}"
    if skill == "reading":
        return f"AR {g('ar'):g}, up to {g('density_p90', 0):.0f} notes on screen"
    if skill == "consistency":
        return f"evenly hard from start to end ({g('evenness', 0):.0%})"
    if skill == "quadrant" and t.quadrant:
        return f"{g('q_' + t.quadrant.replace('-', '_')):.0%} of its jumps land {t.quadrant}"
    return f"{g('stars'):.2f}★, popular"


def map_url(r) -> str:
    bid, sid = int(_f(r.get("beatmap_id"), 0)), int(_f(r.get("beatmapset_id"), 0))
    if sid and bid:
        return f"https://osu.ppy.sh/beatmapsets/{sid}#osu/{bid}"
    return f"https://osu.ppy.sh/b/{bid}" if bid else ""


def recommendations(pool: pd.DataFrame, profile, per_skill: int = 4) -> list[tuple[str, pd.DataFrame]]:
    """Map suggestions for the player's weaknesses (+ weak quadrant) and a level-up set."""
    t = targets_from_profile(profile)
    skills = list(getattr(profile, "weaknesses", []) or [])
    if t.quadrant:
        skills.append("quadrant")
    skills.append("general")
    out, used = [], set()
    for sk in skills:
        df = suggest(pool, sk, t, n=per_skill, exclude=used)
        if not df.empty:
            used |= set(df["md5"])
            out.append((sk, df))
    return out


def skill_label(skill: str, t: Targets | None = None) -> str:
    if skill == "quadrant" and t and t.quadrant:
        return f"Weak quadrant ({t.quadrant})"
    return SKILL_INFO.get(skill, {"label": skill})["label"]


def collection_name(skill: str, t: Targets) -> str:
    return f"osu-coach: {skill_label(skill, t)} ({t.comfort:.1f}★)"

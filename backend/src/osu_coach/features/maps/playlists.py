"""Practice map suggestions and staged "improve a skill" playlists, ranked on the map pool (a data frame)."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from osu_coach.common.texts import why
from osu_coach.domain.maps.suggestions import SKILL_INFO, STAGES, Targets, finite_or, map_url, targets_from_profile


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


def suggest(
    pool: pd.DataFrame,
    skill: str,
    targets: Targets,
    n: int = 10,
    offset: float | None = None,
    width: float = 0.5,
    exclude: set | frozenset = frozenset(),
    min_skill: float = 0.35,
    exclude_titles: set | frozenset = frozenset(),
) -> pd.DataFrame:
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
    if skill == "accuracy":  # timing practice needs tight hit windows *for the player's level*
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
    if win["beatmapset_id"].nunique() < n:  # thin region of the pool: take the closest maps
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
    cand["score"] = (
        0.55 * cand["skill_fit"] + 0.25 * cand["star_fit"] + 0.20 * cand["popularity"] + bpm_w * cand["bpm_fit"]
    )
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


def stream_length_maps(
    pool: pd.DataFrame, targets: Targets, min_run: int, max_run: int, n: int = 6, offset: float = -0.3
) -> pd.DataFrame:
    """Maps whose longest stream is ``min_run``–``max_run`` notes, at a stream speed the player can tap
    (``targets.stream_bpm``) and around his level: for practising streams of exactly that length."""
    if pool is None or pool.empty or "max_run" not in pool:
        return pd.DataFrame()
    sub = pool[(pool["max_run"] >= min_run) & (pool["max_run"] <= max_run)]
    if sub.empty:
        return sub
    out = suggest(sub, "stamina", targets, n=n, offset=offset, min_skill=0.0)
    if not out.empty:
        out["why"] = [
            f"longest stream {int(r['max_run'])} notes at ~{finite_or(r.get('stream_bpm'), finite_or(r.get('burst_bpm'), 0)):.0f}"
            f" BPM (1/4)"
            for _, r in out.iterrows()
        ]
    return out


PLAYLIST_COLUMNS = [
    "stage",
    "goal",
    "stars",
    "artist",
    "title",
    "version",
    "creator",
    "why",
    "url",
    "md5",
    "beatmap_id",
    "beatmapset_id",
    "bpm",
    "ar",
    "od",
    "drain_length",
]


def build_playlist(pool: pd.DataFrame, skill: str, targets: Targets, n: int = 15) -> pd.DataFrame:
    """Three stages (warm-up / core / push) of practice maps for one skill."""
    base_offset = SKILL_INFO.get(skill, SKILL_INFO["general"])["offset"]
    deltas = (-0.3, 0.0, 0.3) if skill == "accuracy" else tuple(d for _, d in STAGES)
    per = [n // 3, n - 2 * (n // 3), n // 3]
    parts, used, titles = [], set(), set()
    for (stage, _), delta, k in zip(STAGES, deltas, per):
        if k <= 0:
            continue
        part = suggest(
            pool, skill, targets, n=k, offset=base_offset + delta, width=0.3, exclude=used, exclude_titles=titles
        )
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
    return {
        "Warm-up": f"Full combo — focus on {focus}",
        "Core": "Under 5 misses, then go for the full combo",
        "Push": "Pass it, then retry the hardest section",
    }[stage]


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

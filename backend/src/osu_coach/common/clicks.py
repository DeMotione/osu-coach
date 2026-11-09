"""Where clicks land: the response model and its conversion, shared by the Aim page and the replay check."""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from osu_coach.common.convert import num
from osu_coach.common.weighted import played_notes, weights_of, wmean, wquantile, wrate, wstd


class ClickBand(BaseModel):
    label: str
    share: float | None


class ClickSummary(BaseModel):
    n: int
    mean_px: list[float | None] = Field(min_length=2, max_length=2, description="[x, y], osu!px.")
    mean_r: list[float | None] = Field(min_length=2, max_length=2, description="[x, y], circle radii.")
    ci_px: float | None
    sd_px: list[float | None] = Field(min_length=2, max_length=2, description="[sideways, up/down], osu!px.")
    radius: float | None
    bands: list[ClickBand]


class Clicks(BaseModel):
    """Where clicks land, in circle radii from the note centre (y down)."""

    view: Literal["screen", "movement"]
    enough: bool
    plays: int = Field(description="Plays the clicks are from.")
    n: int = Field(description="All clicks.")
    drawn: int = Field(description="Clicks in x / y (a weighted random sample).")
    x: list[float]
    y: list[float]
    hit: list[bool]
    summary: ClickSummary | None


CLICKS_MIN = 30


def clicks(objects: pd.DataFrame, view: str) -> Clicks:
    """Where clicks land (a weighted random sample) and the summary of all of them."""
    C = click_points(objects, view)
    plays = int(objects["replay_key"].nunique()) if "replay_key" in objects else 0
    if len(C) < CLICKS_MIN:
        return Clicks(view=view, enough=False, plays=plays, n=len(C), drawn=0, x=[], y=[], hit=[], summary=None)
    s = click_summary(C)
    drawn = click_sample(C)
    labels = [label for _, _, label in CLICK_BANDS]
    summary_out = ClickSummary(
        n=int(s["n"]),
        mean_px=[num(s["mean_px"][0]), num(s["mean_px"][1])],
        mean_r=[num(s["mean_r"][0]), num(s["mean_r"][1])],
        ci_px=num(s["ci_px"]),
        sd_px=[num(s["sd_px"][0]), num(s["sd_px"][1])],
        radius=num(s["radius"]),
        bands=[ClickBand(label=k, share=num(s["bands"].get(k))) for k in labels],
    )
    return Clicks(
        view=view,
        enough=True,
        plays=plays,
        n=len(C),
        drawn=len(drawn),
        x=[round(float(v), 4) for v in drawn["x"]],
        y=[round(float(v), 4) for v in drawn["y"]],
        hit=[bool(v) for v in drawn["hit"]],
        summary=summary_out,
    )


CLICKS_DRAWN = 4000

CLICK_RANGE = 2.4  # radii shown around the circle centre


def click_sample(C: pd.DataFrame, n: int = CLICKS_DRAWN, seed: int = 0) -> pd.DataFrame:
    """One random sample of ``n`` clicks (of :func:`~osu_coach.domain.player.click_points`), so the share of aim
    misses in the picture is the real one. Plays far from the player's level are drawn less often, like
    they count less: weighted sampling without replacement (the ``n`` largest u^(1/w)). Clicks further
    than :data:`CLICK_RANGE` radii from the centre are left out."""
    if len(C) > n:
        w = C["w"].to_numpy(float) if "w" in C else np.ones(len(C))
        keys = np.log(np.random.default_rng(seed).random(len(C))) / np.maximum(w, 1e-12)
        drawn = C.iloc[np.sort(np.argsort(keys)[-n:])]
    else:
        drawn = C
    return drawn[(drawn["x"].abs() < CLICK_RANGE) & (drawn["y"].abs() < CLICK_RANGE)]


CLICK_BANDS = [
    (0.0, 0.25, "≤ ¼"),
    (0.25, 0.5, "¼–½"),
    (0.5, 0.75, "½–¾"),
    (0.75, 1.0, "¾–1"),
    (1.0, math.inf, "outside"),
]


def click_points(O: pd.DataFrame, frame: str = "screen") -> pd.DataFrame:
    """Where clicks land, in circle radii from the note centre: the click that hit each circle /
    slider head, and the closest click of every aim miss (misses without a click aren't clicks).

    ``frame="screen"``: x right, y down, as on screen — every hit note. ``"movement"``: jumps only,
    rotated so each jump goes right (x = overshoot, y = clockwise side); a constant offset averages
    out in this frame, so it can only be seen on screen. ``w`` = replay weight."""
    P = played_notes(O)
    S = P[P["head_hit"] | (P["miss_reason"] == "aim")]
    if frame == "movement":
        S = S[S["dist_norm"] >= 1]
        x, y = S["along"], S["cross"]
    else:
        x, y = S["err_dx"] / S["radius"], S["err_dy"] / S["radius"]
    out = pd.DataFrame(
        {
            "x": x.to_numpy(float),
            "y": y.to_numpy(float),
            "radius": S["radius"].to_numpy(float),
            "hit": S["head_hit"].to_numpy(bool),
            "w": weights_of(S).to_numpy(float),
        }
    )
    return out.dropna(subset=["x", "y"]).reset_index(drop=True)


def click_summary(C: pd.DataFrame) -> dict:
    """Average click (osu!px, with a 95% margin), spread, and the share of clicks by distance from the
    centre (``bands``, "outside" = beyond the circle's edge). Weighted by ``w`` if present."""
    n = len(C)
    if not n:
        return {"n": 0}
    w = weights_of(C)
    px, py = C["x"] * C["radius"], C["y"] * C["radius"]
    d = pd.Series(np.hypot(C["x"], C["y"]), index=C.index)
    sd = (wstd(px, w), wstd(py, w)) if n > 1 else (math.nan, math.nan)
    neff = float(w.sum() ** 2 / max(float((w**2).sum()), 1e-12))
    ci = 1.96 * math.hypot(*sd) / math.sqrt(2 * neff) if n > 1 else math.nan
    bands = {label: wrate((d > lo) & (d <= hi) if lo > 0 else (d <= hi), w) for lo, hi, label in CLICK_BANDS}
    return {
        "n": n,
        "mean_px": (wmean(px, w), wmean(py, w)),
        "mean_r": (wmean(C["x"], w), wmean(C["y"], w)),
        "ci_px": ci,
        "sd_px": sd,
        "median_r": wquantile(d, w, 0.5),
        "outside": bands["outside"],
        "bands": bands,
        "radius": float(C["radius"].median()),
    }

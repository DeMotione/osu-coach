"""Chart-style analyses that more than one page shows."""

from __future__ import annotations

import pandas as pd

from osu_coach.app.convert import num
from osu_coach.insights import domain as insights
from osu_coach.insights.schemas import ClickBand, Clicks, ClickSummary
from osu_coach.profile.domain import CLICK_BANDS, click_points, click_summary

CLICKS_MIN = 30


def clicks(objects: pd.DataFrame, view: str) -> Clicks:
    """Where clicks land (a weighted random sample) and the summary of all of them."""
    C = click_points(objects, view)
    if len(C) < CLICKS_MIN:
        return Clicks(view=view, enough=False, n=len(C), drawn=0, x=[], y=[], hit=[], summary=None)
    s = click_summary(C)
    drawn = insights.click_sample(C)
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
        n=len(C),
        drawn=len(drawn),
        x=[round(float(v), 4) for v in drawn["x"]],
        y=[round(float(v), 4) for v in drawn["y"]],
        hit=[bool(v) for v in drawn["hit"]],
        summary=summary_out,
    )

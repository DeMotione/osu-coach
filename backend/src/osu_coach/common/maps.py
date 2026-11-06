from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, Field

from osu_coach.common.convert import integer, num, text


class MapRow(BaseModel):
    """One beatmap of the bundled pool, as listed in suggestions and playlists."""

    md5: str
    beatmap_id: int
    beatmapset_id: int
    artist: str
    title: str
    version: str
    creator: str | None = None
    stars: float | None = Field(description="Star rating for the exact map configuration.")
    configuration_id: str | None = Field(None, description="Complete map, mods, rate, client, and settings identity.")
    mods: str = "NM"
    rate: float = 1.0
    bpm: float | None
    ar: float | None
    od: float | None = None
    length_s: float | None = Field(description="Drain time in seconds.")
    why: str = Field(description="Why the map was picked: the patterns it has for the skill.")
    url: str
    stage: str | None = Field(None, description="Playlist stage (Warm-up / Core / Push) or suggestion section.")
    goal: str | None = Field(None, description="What to aim for on this stage.")
    skill_demand: float | None = Field(None, description="Experimental map demand on the 0–100 skill scale.")
    relevance: float | None = Field(None, description="Target skill training relevance, 0–1.")
    formula_score: float | None = Field(None, description="F(m), comparable within one goal.")
    breakdown: dict | None = Field(None, description="The terms of the ranking formula and its inputs.")


def map_rows(df: pd.DataFrame | None) -> list[MapRow]:
    if df is None or df.empty:
        return []
    return [
        MapRow(
            md5=str(r["md5"]),
            beatmap_id=integer(r.get("beatmap_id")) or 0,
            beatmapset_id=integer(r.get("beatmapset_id")) or 0,
            artist=text(r.get("artist")) or "",
            title=text(r.get("title")) or "",
            version=text(r.get("version")) or "",
            creator=text(r.get("creator")),
            stars=num(r.get("stars")),
            configuration_id=text(r.get("configuration_id")),
            mods=text(r.get("mods")) or "NM",
            rate=num(r.get("rate")) or 1.0,
            bpm=num(r.get("bpm")),
            ar=num(r.get("ar")),
            od=num(r.get("od")),
            length_s=num(r.get("drain_length")),
            why=text(r.get("why")) or "",
            url=text(r.get("url")) or "",
            stage=text(r.get("stage")),
            goal=text(r.get("goal")),
            skill_demand=num(r.get("skill_demand")),
            relevance=num(r.get("relevance")),
            formula_score=num(r.get("formula_score")),
            breakdown=r.get("breakdown") if isinstance(r.get("breakdown"), dict) else None,
        )
        for r in df.to_dict("records")
    ]

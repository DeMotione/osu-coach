from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict

from pydantic import BaseModel, Field

from osu_coach.common.convert import integer, num, text
from osu_coach.domain.maps.skillset import RankedMap


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


def map_rows(maps: Iterable[RankedMap], stage: str | None = None, goal: str | None = None) -> list[MapRow]:
    """The recommended maps as listed, with their ``stage`` and ``goal``."""
    rows = []
    for m in maps:
        r = m.map
        rows.append(
            MapRow(
                md5=m.md5,
                beatmap_id=integer(r.get("beatmap_id")) or 0,
                beatmapset_id=integer(r.get("beatmapset_id")) or 0,
                artist=text(r.get("artist")) or "",
                title=text(r.get("title")) or "",
                version=text(r.get("version")) or "",
                creator=text(r.get("creator")),
                stars=num(r.get("stars")),
                configuration_id=m.configuration_id,
                mods=m.mods or "NM",
                rate=num(m.rate) or 1.0,
                bpm=num(r.get("bpm")),
                ar=num(r.get("ar")),
                od=num(r.get("od")),
                length_s=num(r.get("drain_length")),
                why=m.why,
                url=m.url,
                stage=stage,
                goal=goal,
                skill_demand=num(m.skill_demand),
                relevance=num(m.relevance),
                formula_score=num(m.formula_score),
                breakdown=asdict(m.breakdown),
            )
        )
    return rows

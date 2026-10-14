from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from osu_coach.app.schemas import Request


class MapRow(BaseModel):
    """One beatmap of the bundled pool, as listed in suggestions and playlists."""

    md5: str
    beatmap_id: int
    beatmapset_id: int
    artist: str
    title: str
    version: str
    creator: str | None = None
    stars: float | None = Field(description="Star rating (no mod).")
    bpm: float | None
    ar: float | None
    od: float | None = None
    length_s: float | None = Field(description="Drain time in seconds.")
    why: str = Field(description="Why the map was picked: the patterns it has for the skill.")
    url: str
    stage: str | None = Field(None, description="Playlist stage (Warm-up / Core / Push) or suggestion section.")
    goal: str | None = Field(None, description="What to aim for on this stage.")


class SuggestionSection(BaseModel):
    skill: str
    title: str
    score: float | None = Field(description="The player's score of that skill (weak skills).")
    maps: list[MapRow]


class Suggestions(BaseModel):
    comfort: float
    pool_size: int
    hidden: int
    sections: list[SuggestionSection]
    collection_name: str
    preferred_client: Literal["stable", "lazer"]


class HideMaps(Request):
    md5s: list[Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]] = Field(min_length=1, max_length=500)


class PlaylistSkill(BaseModel):
    key: str
    label: str
    score: float | None


class PlaylistStage(BaseModel):
    stage: str
    goal: str
    maps: list[MapRow]


class Playlist(BaseModel):
    skill: str
    skills: list[PlaylistSkill]
    default_skill: str
    has_profile: bool
    comfort: float
    stream_bpm: float | None
    maps: int
    collection_name: str
    stages: list[PlaylistStage]
    preferred_client: Literal["stable", "lazer"]

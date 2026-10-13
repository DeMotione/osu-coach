"""Shared response models."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Request(BaseModel):
    """Base of request bodies: unknown fields are an error, not silently ignored."""
    model_config = ConfigDict(extra="forbid")


class Choice(BaseModel):
    key: str
    label: str


class Count(BaseModel):
    """A reason / name with how often it occurs."""
    label: str
    count: int


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

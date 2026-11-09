from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from osu_coach.common.jobs import JobBase
from osu_coach.common.maps import MapRow
from osu_coach.common.schemas import Request


class SuggestionSection(BaseModel):
    skill: str
    title: str
    score: float | None = Field(description="The player's score of that skill (weak skills).")
    maps: list[MapRow]
    target_stars: float | None = None
    target_demand: float | None = None
    skill_adjusted_stars: float | None = None
    eligible: int = 0
    excluded: dict[str, int] = Field(default_factory=dict)


class Suggestions(BaseModel):
    comfort: float
    comfort_source: str = Field(
        description="Replay comfort, manual input, recent level fallback, or stated assumption."
    )
    pool_size: int
    hidden: int
    sections: list[SuggestionSection]
    collection_name: str
    preferred_client: Literal["stable", "lazer"]
    has_profile: bool = False
    unmeasured_skills: list[str] = Field(default_factory=list)


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
    target_stars: float | None = None
    target_demand: float | None = None
    eligible: int = 0
    excluded: dict[str, int] = Field(default_factory=dict)


class Playlist(BaseModel):
    skill: str
    skills: list[PlaylistSkill]
    default_skill: str
    has_profile: bool
    comfort: float
    comfort_source: str = Field(
        description="Replay comfort, manual input, recent level fallback, or stated assumption."
    )
    stream_bpm: float | None
    maps: int
    collection_name: str
    stages: list[PlaylistStage]
    preferred_client: Literal["stable", "lazer"]
    skill_adjusted_stars: float | None = None
    abilities: dict[str, float] = Field(default_factory=dict)
    measured_abilities: dict[str, float] = Field(
        default_factory=dict, description="Replay-derived skill ratings before manual overrides."
    )
    coverage_maps: int | None = Field(
        None, description="Maps with verified .osu data searched for modified configurations."
    )
    unavailable_maps: int | None = Field(None, description="Pool maps whose verified .osu data was unavailable.")
    calculator_unavailable_maps: int | None = Field(
        None, description="Verified maps whose supported difficulty calculation was unavailable."
    )
    unavailable_configurations: int | None = Field(
        None,
        description="Configurations on verified maps whose exact calculation was unavailable, including partial maps.",
    )
    result_limit: int | None = Field(
        None, description="Maximum distinct ranked maps returned per stage; eligible counts include all selected maps."
    )


class PlaylistSearchRequest(Request):
    skill: str | None = None
    comfort: float | None = Field(None, gt=0)
    assessed: str | None = None
    ratings: str | None = None
    kappa: float = Field(0.5, ge=0)
    min_relevance: float = Field(0.3, ge=0, le=1)
    exclude_played: bool = True
    allow_hr: bool = False
    allow_hd: bool = False
    adjustable_dt: bool = False
    min_rate: float = Field(1.10, ge=1.10, le=2.00)
    max_rate: float = Field(2.00, ge=1.10, le=2.00)


class PlaylistJob(JobBase):
    kind: Literal["playlist"]
    result: Playlist | None

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from osu_coach.common.schemas import Request

Period = Literal["month", "week", "day"]
ProgressReplays = Literal["analysed", "all"]
# what a goal's values are counted in: the 0–100 score, or the map star rating (Star Levels, #129)
Unit = Literal["score", "stars"]


class ProgressPlayer(BaseModel):
    name: str
    plays: int


class StarRange(BaseModel):
    stars: float | None = Field(description="The star rating the skill holds up on.")
    low: float | None = Field(description="Its 90% range: the lower end.")
    high: float | None


class PeriodRow(BaseModel):
    key: str = Field(description="YYYY-MM, YYYY-Www or YYYY-MM-DD.")
    plays: int
    maps: int
    new_maps: int
    minutes: float | None
    comfort_stars: float | None
    avg_stars: float | None
    max_stars_passed: float | None
    max_stars_passed_map: str | None = Field(
        default=None, description="The hardest clean pass: 'Artist - Title [Difficulty] +MODS' (no '+…' without mods)."
    )
    max_stars_fc: float | None
    accuracy: float | None
    misses_per_100: float | None
    ur: float | None
    stream_bpm: float | None
    few_plays: bool
    skills: dict[str, float | None] = Field(
        description="The Overview's skill ratings, 0–100: 50 = expected at the reference comfort level (``skill_reference_stars``)."
    )
    star_levels: dict[str, StarRange] = Field(
        default_factory=dict,
        description="Star Levels: each skill's star level fitted to the period's plays alone (every play saved of it); "
        "only the skills it could be fitted for.",
    )


class ProgressOut(BaseModel):
    player: str
    period: Period
    replays: ProgressReplays = Field(
        default="all",
        description="analysed = only the replays of the last analysis (the ones the Overview shows, rated at its "
        "comfort level); all = every play saved for the player.",
    )
    analysed_plays: int | None = Field(
        default=None, description="How many of the player's replays the last analysis holds; null = none."
    )
    first_day: dt.date | None = Field(description="Day of the first saved play.")
    skill_reference_stars: float | None = Field(
        description="The comfort level (★) every period's skill ratings are measured against; null = none saved."
    )
    unit: Unit = Field(
        "score", description="What the chosen engine rates skills in: score (skills) or stars (star_levels)."
    )
    rows: list[PeriodRow]


class ProgressPlay(BaseModel):
    played_at: str | None
    map: str
    mods: str
    stars: float | None
    accuracy: float | None
    misses: int | None
    combo: int | None
    map_combo: int | None
    result: Literal["full combo", "passed", "failed"]


class GoalOut(BaseModel):
    id: str
    skill: str
    label: str
    start: float | None
    target: float
    created: dt.date
    deadline: dt.date
    done: dt.date | None
    current: float | None
    progress: float | None
    left: float | None
    days_left: int
    state: Literal["done", "on track", "behind", "overdue", "no data", "paused"]
    score_source: Literal["experimental", "legacy"] = Field(description="Rating scale used when the goal was created.")
    unit: Unit = Field("score", description="What start, target, current and left are in: the score, or stars.")
    paused_reason: Literal["old_scale", "accuracy", "unit"] | None = Field(
        None,
        description="Why a paused goal isn't followed: set on the scores before 0.10, a recalibrated accuracy goal, "
        "or set as a score where the skill is now in stars.",
    )


class SkillValue(BaseModel):
    key: str
    label: str
    score: float = Field(description="Its 0–100 score (weak at 45 or less).")
    value: float = Field(description="What a goal for it follows now, in ``unit``.")
    unit: Unit = "score"


class SuggestedGoal(BaseModel):
    skill: str
    label: str
    current: float
    target: float
    unit: Unit = "score"


class HistoryPoint(BaseModel):
    day: str
    score: float | None = Field(description="The skill's value that day, in the goal's unit.")


class GoalHistory(BaseModel):
    goal_id: str
    skill: str
    label: str
    unit: Unit = "score"
    points: list[HistoryPoint] = Field(
        description="Day by day for a score goal of Comfort Score (the saved history); otherwise today's value."
    )
    target: list[HistoryPoint] = Field(description="From the start score on the day it was set to the target.")


class GoalsOut(BaseModel):
    has_profile: bool
    open: list[GoalOut]
    done: list[GoalOut]
    behind: int
    skills: list[SkillValue] = Field(description="Skills with a score: the ones a goal can be set for.")
    suggested: list[SuggestedGoal] = Field(
        description="A 4-week plan for up to 3 measured skills rated 45 or lower in Overview, without open goals."
    )
    weak_without_goal: list[SkillValue]
    history: list[GoalHistory]


class GoalCreate(Request):
    skill: str
    target: float = Field(ge=1, le=100)
    deadline: dt.date

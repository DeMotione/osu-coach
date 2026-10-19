from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from osu_coach.app.schemas import Request

Period = Literal["month", "week", "day"]


class ProgressPlayer(BaseModel):
    name: str
    plays: int


class PeriodRow(BaseModel):
    key: str = Field(description="YYYY-MM, YYYY-Www or YYYY-MM-DD.")
    plays: int
    maps: int
    new_maps: int
    minutes: float | None
    comfort_stars: float | None
    avg_stars: float | None
    max_stars_passed: float | None
    max_stars_fc: float | None
    accuracy: float | None
    misses_per_100: float | None
    ur: float | None
    stream_bpm: float | None
    few_plays: bool
    skills: dict[str, float | None] = Field(description="Skill scores (50 = all-time average at that difficulty).")


class ProgressOut(BaseModel):
    player: str
    period: Period
    first_day: dt.date | None = Field(description="Day of the first saved play.")
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


class SkillValue(BaseModel):
    key: str
    label: str
    score: float


class SuggestedGoal(BaseModel):
    skill: str
    label: str
    current: float
    target: float


class HistoryPoint(BaseModel):
    day: str
    score: float | None


class GoalHistory(BaseModel):
    goal_id: str
    skill: str
    label: str
    points: list[HistoryPoint]
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

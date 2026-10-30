from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from osu_coach.app.schemas import Request
from osu_coach.jobs.schemas import JobBase

GoalKind = Literal["fc", "farm", "mod"]
GoalMods = Literal["NM", "HD", "HR", "HDHR", "DT", "HDDT", "HRDT", "HDHRDT"]
TrainingMods = Literal["HD", "HR", "HDHR", "DT", "HDDT", "HRDT", "HDHRDT"]
GoalClient = Literal["stable", "lazer"]


class PlayGoalRequest(Request):
    goal: GoalKind = "fc"
    replay_path: str | None = Field(None, max_length=4000)
    beatmap: str | None = Field(None, max_length=500, description="An osu.ppy.sh difficulty link.")
    mods: GoalMods = "NM"
    client: GoalClient = "stable"
    training_mod: TrainingMods = "HD"
    farm_mods: list[GoalMods] = Field(
        default_factory=lambda: ["NM", "HD", "HR", "DT", "HDDT"], min_length=1, max_length=8
    )
    online: bool = True
    min_pp: float | None = Field(None, ge=0, le=5000, description="Hide maps whose FC scenario gives less PP.")

    @model_validator(mode="after")
    def target_required(self):
        if self.goal == "fc" and bool(self.replay_path) == bool(self.beatmap and self.beatmap.strip()):
            raise ValueError("Choose one replay or one beatmap difficulty for the FC goal.")
        return self


class GoalMap(BaseModel):
    md5: str
    beatmap_id: int
    beatmapset_id: int
    artist: str
    title: str
    version: str
    mods: GoalMods
    client: GoalClient
    stars: float
    bpm: float
    ar: float
    od: float
    length_s: float
    dynamics: str | None = Field(
        None, description="The map's overall character, e.g. Streamy or Jumpy + Reading-heavy."
    )


class AccuracyEstimate(BaseModel):
    low: float = Field(ge=0, le=1)
    high: float = Field(ge=0, le=1)
    median: float = Field(ge=0, le=1)
    plays: int
    maps: int
    explanation: str


class GoalBlocker(BaseModel):
    skill: str
    title: str
    detail: str
    timestamps: list[str]
    observed: bool = False


class GoalRecommendation(BaseModel):
    map: GoalMap
    why: str
    objective: str
    step_up: str
    accuracy: AccuracyEstimate | None = None
    practice_accuracy: float = Field(ge=0, le=1)
    pp: float | None = Field(None, ge=0)
    pp_ss: float | None = Field(None, ge=0, description="PP for a 100% FC.")
    pp_label: str | None = None
    pp_accuracy: float | None = Field(None, ge=0, le=1)
    local_best_accuracy: float | None = None
    achieved: bool = False
    stage: Literal["Starter", "Core", "Stretch"] = "Core"


class PlayGoalResult(BaseModel):
    request: PlayGoalRequest
    evidence_revision: str
    player: str | None
    status: Literal["assessed", "insufficient_evidence", "partial"]
    verdict: str
    tone: Literal["good", "warn", "bad", "info"] = "info"
    reasons: list[str]
    confidence: Literal["unassessed", "limited", "moderate"]
    target: GoalMap | None = None
    accuracy: AccuracyEstimate | None = None
    blockers: list[GoalBlocker]
    recommendations: list[GoalRecommendation]
    warnings: list[str]
    coverage_maps: int
    replay_path: str | None = None


class PlayGoalJob(JobBase):
    kind: Literal["play_goal"]
    result: PlayGoalResult | None


class PlayGoalOptions(BaseModel):
    last_request: PlayGoalRequest | None
    evidence_revision: str
    player: str | None
    players: list[str]
    evidence_plays: int
    coverage_maps: int

"""Responses and requests of the "analyse replays" use case."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from osu_coach.app.schemas import Request
from osu_coach.jobs.schemas import JobBase
from osu_coach.replays.schemas import DateRange, Latest


class AnalysisRequest(Request):
    player: str | None = Field(None, description="Player to analyse; '*' = all; null = the one with most replays.")
    latest: Latest = Latest.newest_500
    date_range: DateRange = "all"
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    online: bool = Field(True, description="Download missing beatmaps (osu.direct lookup, osu.ppy.sh file).")


class AnalysisResult(BaseModel):
    analysed: int
    skipped: int
    best_replays: int | None = Field(description="With Best replays chosen: how many of them are best replays.")
    profile_ready: bool
    warnings: list[str]


class SkippedReplay(BaseModel):
    file: str
    reason: str


class AnalysisStatus(BaseModel):
    analysed: int
    player_label: str
    replay_set: Literal["all", "best"]
    profile_replays: int | None = Field(description="Replays in the profile (after Best replays); null = none.")
    best_empty: bool
    skipped: list[SkippedReplay] = Field(description="First 200 skipped replays.")
    skipped_total: int


class AnalysisJob(JobBase):
    kind: Literal["analysis"]
    result: AnalysisResult | None

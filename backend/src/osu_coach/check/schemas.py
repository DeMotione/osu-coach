"""Detailed Map Analysis: one play on its own."""

from __future__ import annotations

from pydantic import BaseModel, Field

from osu_coach.app.schemas import Request
from osu_coach.insights.schemas import Clicks


class CheckReplay(BaseModel):
    path: str
    played_at: str | None
    player: str
    map: str
    mods: str
    accuracy: float | None
    beatmap_md5: str | None
    analysable: bool
    reason: str | None = Field(description="Why it can't be checked.")


class CheckList(BaseModel):
    available: bool = Field(description="False: no osu! install found and nothing scanned or uploaded.")
    replays: list[CheckReplay] = Field(description="Newest first.")
    selected: str | None = Field(description="Path of the replay to show (the one asked for, else the newest).")
    focus_md5: str | None
    only_map: bool


class CheckRequest(Request):
    path: str = Field(min_length=1, max_length=4000)
    online: bool = Field(True, description="Download the beatmap if it's missing.")


class CheckSummary(BaseModel):
    player: str
    played_at: str | None
    map: str
    mods_label: str
    client: str | None
    creator: str | None
    beatmap_id: int | None
    accuracy: float | None
    combo: int | None
    map_combo: int | None
    misses: int
    slider_breaks: int
    stars: float | None
    bpm: float | None
    ur: float | None
    rate: float
    ar: float | None
    od: float | None
    cs: float | None
    hp: float | None
    length_s: float | None
    completed: bool
    sim_exact: bool
    sim_agreement: float | None
    verdict: list[str]


class CheckEvent(BaseModel):
    time: float
    timestamp: str = Field(description="Map time as the osu! editor shows it (mm:ss:mmm).")
    what: str
    reason: str
    reason_label: str
    detail: str
    pattern: str


class SectionReason(BaseModel):
    reason: str
    label: str
    count: int


class PracticeSection(BaseModel):
    start: str
    end: str
    seconds: float
    notes: int
    count: int
    reasons: list[SectionReason]
    pattern: str
    first_event: str
    last_event: str


class TimingMark(BaseModel):
    time: float
    what: str
    label: str


class PlayTiming(BaseModel):
    time: list[float] = Field(description="Map time of every hit, ms.")
    error: list[float] = Field(description="Hit error, ms (− early, + late).")
    result: list[int]
    trend: list[float | None]
    window_300: float | None
    top: float
    length_ms: float
    marks: list[TimingMark] = Field(description="Misses and combo breaks.")


class MapPlay(BaseModel):
    this: bool
    same_settings: bool
    played_at: str | None
    mods_label: str
    settings_label: str
    bpm: float | None
    stars: float | None
    accuracy: float | None
    misses: int | None
    combo: int | None
    ur: float | None
    passed: bool | None
    path: str
    path_exists: bool


class MapPlays(BaseModel):
    first: bool = Field(description="First play of this map in the saved history.")
    settings: str
    same_settings_plays: int
    best_misses: int | None
    best_accuracy: float | None
    is_best: bool | None
    ur_median: float | None
    other_settings: int
    rows: list[MapPlay]


class CheckReport(BaseModel):
    path: str
    summary: CheckSummary
    events: list[CheckEvent]
    sections: list[PracticeSection]
    timing: PlayTiming | None
    map_plays: MapPlays
    clicks_screen: Clicks | None
    clicks_movement: Clicks | None

from __future__ import annotations

import datetime as dt
from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .common import Request


class Latest(IntEnum):
    """How many of the newest replays to read; 0 = all of them."""
    newest_100 = 100
    newest_500 = 500
    newest_1000 = 1000
    all = 0


DateRange = Literal["all", "session", "7d", "30d", "custom"]
ReplaySet = Literal["all", "best"]
SourceMode = Literal["library", "files"]


class AppSettings(BaseModel):
    """Choices remembered across starts (``settings.json`` in the data folder, shared with the command line)."""
    source_mode: SourceMode = "library"
    folders: str = Field("", description="Extra replay folders, one per line.")
    latest: Latest = Field(Latest.newest_500, description="Newest replays to read; 0 = all.")
    date_range: DateRange = "all"
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    replay_set: ReplaySet = "all"
    level_override: float | None = Field(None, description="Level (★) set by hand; null = detected.")
    player: str | None = Field(None, description="Player analysed last; '*' = all players.")
    manual_comfort: float = Field(2.5, description="Star rating for playlists without analysed replays.")
    setup_saved: bool = False


class SettingsPatch(Request):
    """Fields to change; fields left out stay as they are (``null`` clears a nullable one)."""
    source_mode: SourceMode | None = None
    folders: str | None = Field(None, max_length=20000)
    latest: Latest | None = None
    date_range: DateRange | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    replay_set: ReplaySet | None = None
    level_override: float | None = Field(None, ge=1.0, le=12.0)
    player: str | None = Field(None, max_length=200)
    manual_comfort: float | None = Field(None, ge=1.0, le=8.0)


class SetupModel(BaseModel):
    """The player's setup: makes the tips concrete (tablet area, sensitivity, keyboard / SayoDevice)."""
    device: Literal["tablet", "mouse"] = "tablet"
    handedness: Literal["right", "left"] = "right"
    client: Literal["stable", "lazer"] = "stable"
    area_w_mm: float | None = Field(None, ge=0, le=500)
    area_h_mm: float | None = Field(None, ge=0, le=500)
    area_x_mm: float | None = Field(None, ge=0, le=500, description="Area centre (OpenTabletDriver X).")
    area_y_mm: float | None = Field(None, ge=0, le=500, description="Area centre (OpenTabletDriver Y).")
    screen_w_px: int = Field(1920, ge=640, le=7680)
    screen_h_px: int = Field(1080, ge=480, le=4320)
    mouse_dpi: int | None = Field(None, ge=0, le=50000)
    ingame_sens: float | None = Field(None, ge=0, le=10)
    keyboard: Literal["standard", "rapid_trigger", "sayo"] = "standard"
    actuation_mm: float | None = Field(None, ge=0, le=4)
    rt_press_mm: float | None = Field(None, ge=0, le=2)
    rt_release_mm: float | None = Field(None, ge=0, le=2)
    sayo_stroke_mm: float | None = Field(None, ge=0, le=6)
    sayo_trigger_mm: float | None = Field(None, ge=0, le=6)
    sayo_release_mm: float | None = Field(None, ge=0, le=6)
    sayo_rt: bool | None = None
    sayo_rt_trigger_mm: float | None = Field(None, ge=0, le=6)
    sayo_rt_release_mm: float | None = Field(None, ge=0, le=6)
    sayo_full_stroke: bool | None = None
    sayo_rt_upper_mm: float | None = Field(None, ge=0, le=6)
    sayo_rt_lower_mm: float | None = Field(None, ge=0, le=6)

    @field_validator("area_w_mm", "area_h_mm", "mouse_dpi", "actuation_mm", "rt_press_mm", "rt_release_mm")
    @classmethod
    def _zero_is_unknown(cls, v):
        return v or None


class SetupUpdate(SetupModel, Request):
    pass

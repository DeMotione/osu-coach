from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from osu_coach.common.schemas import Request
from osu_coach.common.setup import SetupModel
from osu_coach.domain.replays.selection import DateRange, Latest, SourceMode

ReplaySet = Literal["all", "best"]
RatingEngine = Literal["comfort", "irt"]


class AppSettings(BaseModel):
    """Choices remembered across starts (``settings.json`` in the data folder, shared with the command line)."""

    source_mode: SourceMode = "library"
    folders: str = Field("", description="Extra replay folders, one per line.")
    latest: Latest = Field(Latest.newest_500, description="Newest of the found replays to analyse; 0 = all.")
    date_range: DateRange = "all"
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    replay_set: ReplaySet = "all"
    rating_engine: RatingEngine = Field(
        "comfort", description="The engine that makes the skill ratings; irt (Star-Scale IRT) is experimental."
    )
    level_override: float | None = Field(None, description="Level (★) set by hand; null = detected.")
    player: str | None = Field(None, description="Player analysed last; '*' = all players.")
    manual_comfort: float = Field(2.5, description="Star rating for playlists without analysed replays.")
    setup_saved: bool = False
    onboarded: bool = Field(False, description="The first-start setup guide was finished or skipped.")
    auto_analyse: bool = Field(
        True, description="Analyse new plays by themselves: the replays osu! saves while osu! coach runs."
    )


class SettingsPatch(Request):
    """Fields to change; fields left out stay as they are (``null`` clears a nullable one)."""

    source_mode: SourceMode | None = None
    folders: str | None = Field(None, max_length=20000)
    latest: Latest | None = None
    date_range: DateRange | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    replay_set: ReplaySet | None = None
    rating_engine: RatingEngine | None = None
    level_override: float | None = Field(None, ge=1.0, le=12.0)
    player: str | None = Field(None, max_length=200)
    manual_comfort: float | None = Field(None, ge=1.0, le=8.0)
    onboarded: bool | None = None
    auto_analyse: bool | None = None


class SetupUpdate(SetupModel, Request):
    pass

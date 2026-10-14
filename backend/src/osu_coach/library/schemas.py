"""Responses and requests of the replay library: finding replays, choosing and analysing them."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from osu_coach.app.schemas import Count, Request
from osu_coach.jobs.schemas import JobBase
from osu_coach.replays.schemas import DateRange, Latest, SourceMode


class InstallOut(BaseModel):
    kind: Literal["stable", "lazer"]
    root: str
    label: str
    songs: str | None
    replay_dirs: list[str]
    files_dir: str | None
    collection_db: str | None


class UploadedFile(BaseModel):
    id: str = Field(description="Use this in a scan request (``files``).")
    name: str
    path: str
    kind: Literal["replay", "beatmap"]
    size: int


class ScanRequest(Request):
    mode: SourceMode = Field("library", description="library = osu! installs and folders; files = only uploads.")
    installs: list[str] | None = Field(None, description="Roots of the installs to scan; null = all found.")
    folders: list[str] = Field(default_factory=list, max_length=50)
    files: list[str] = Field(default_factory=list, max_length=2000, description="Ids of uploaded files.")
    latest: Latest = Field(Latest.newest_500, description="Read only the newest N replays; 0 = all.")


class RescanRequest(Request):
    latest: Latest


class ScanResult(BaseModel):
    replays: int = Field(description="osu!standard replays found.")
    players: int
    scan_limit: int | None = Field(description="Newest replays read per source; null = all.")
    warnings: list[str]


class PlayerCount(BaseModel):
    name: str
    replays: int


class LibraryOut(BaseModel):
    scanned: bool
    mode: SourceMode | None
    sources: list[str]
    scan_limit: int | None
    replays: int
    players: list[PlayerCount]


class SelectionOut(BaseModel):
    """Which of the found replays an analysis with these choices would read."""
    player: str = Field(description="Resolved player; '*' = all players.")
    players: list[PlayerCount]
    files_mode: bool
    replays: int = Field(description="Replays that would be analysed.")
    found: int = Field(description="Replays of the player found by the scan.")
    newest_only: bool = Field(description="Only the newest of the found replays are analysed.")
    missing_maps: int = Field(description="Beatmaps of these replays not on this computer.")
    date_range: DateRange
    date_from: dt.date | None
    date_to: dt.date | None
    empty_range: bool = Field(description="No replays in the chosen time range.")
    older_hint: bool = Field(description="A limited scan may have missed older replays of this player.")
    left_out: list[Count] = Field(description="Replays that can't be analysed, by reason (top 3).")
    left_out_total: int


class ScanJob(JobBase):
    kind: Literal["scan"]
    result: ScanResult | None



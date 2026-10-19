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


class InstallPath(Request):
    path: str = Field(
        min_length=1,
        max_length=1000,
        description="An osu!stable folder (with osu!.exe and Songs) or an osu!lazer data folder (with files/).",
    )


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
    files: list[str] = Field(
        default_factory=list,
        max_length=2000,
        description="Ids of uploaded files, added to the ones added by earlier scans (``LibraryOut.files``).",
    )


class ScanResult(BaseModel):
    replays: int = Field(description="osu!standard replays found: every one in the sources.")
    players: int
    warnings: list[str]


class PlayerCount(BaseModel):
    name: str
    replays: int


class LibraryOut(BaseModel):
    scanned: bool
    mode: SourceMode | None
    sources: list[str]
    replays: int
    players: list[PlayerCount]
    files: list[UploadedFile] = Field(
        description="Replay and beatmap files added by hand: kept, so the next scan adds to them."
    )


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
    left_out: list[Count] = Field(description="Replays that can't be analysed, by reason (top 3).")
    left_out_total: int


class ScanJob(JobBase):
    kind: Literal["scan"]
    result: ScanResult | None


class AnalysisRequest(Request):
    player: str | None = Field(None, description="Player to analyse; '*' = all; null = the one with most replays.")
    latest: Latest = Field(Latest.newest_500, description="Analyse only the newest N of the found replays; 0 = all.")
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

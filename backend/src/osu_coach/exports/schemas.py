from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from osu_coach.app.schemas import Request
from osu_coach.jobs.schemas import JobBase

MD5 = Field(pattern=r"^[0-9a-f]{32}$")


class ExportMap(Request):
    md5: str = MD5
    beatmapset_id: int = Field(ge=1)


class ExportRequest(Request):
    name: str = Field(min_length=1, max_length=200, description="Collection name.")
    maps: list[ExportMap] = Field(min_length=1, max_length=500)


class ExportPreview(BaseModel):
    collection: str
    preferred_client: Literal["stable", "lazer"]
    total_sets: int
    lazer_sets: int = Field(description="Map sets the lazer import folder would download.")
    lazer_approximate: bool = Field(description="Not all of lazer's files were read yet: an upper bound.")
    lazer_folder: str
    stable_available: bool = Field(description="An osu!stable install to add the collection to was found.")
    osz_folder: str = Field(description="Default folder for .osz downloads (stable's Songs folder if found).")


class LazerPackResult(BaseModel):
    path: str
    maps: list[int]
    failed: list[int]


class StableMergeResult(BaseModel):
    path: str
    backup: str | None


class OszRequest(Request):
    folder: str = Field(min_length=1, max_length=1000)
    set_ids: list[int] = Field(min_length=1, max_length=500)


class OszResult(BaseModel):
    folder: str
    downloaded: int
    failed: list[int]


class LazerPackJob(JobBase):
    kind: Literal["lazer_pack"]
    result: LazerPackResult | None


class OszJob(JobBase):
    kind: Literal["osz_download"]
    result: OszResult | None

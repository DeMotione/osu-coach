from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from osu_coach.common.jobs import JobBase
from osu_coach.common.schemas import Request

MD5 = Field(pattern=r"^[0-9a-f]{32}$")


class ExportMap(Request):
    md5: str = MD5
    beatmapset_id: int = Field(
        description="The map's beatmap set on the osu! website; 0 (or less) when it isn't known, e.g. a map that "
        "isn't on the website. Such a map is still put in the collection.",
    )


class ExportRequest(Request):
    name: str = Field(min_length=1, max_length=200, description="Collection name.")
    maps: list[ExportMap] = Field(min_length=1, max_length=10000)


class ExportPreview(BaseModel):
    collection: str
    preferred_client: Literal["stable", "lazer"]
    total_sets: int
    lazer_sets: int = Field(description="Map sets that would be downloaded and sent to lazer.")
    lazer_approximate: bool = Field(
        description="An upper bound: not all of lazer's files were read yet, or some maps' sets are only looked up "
        "when they are sent."
    )
    stable_available: bool = Field(description="An osu!stable install to add the collection to was found.")
    osz_folder: str = Field(description="Default folder for .osz downloads (stable's Songs folder if found).")


class LazerSendResult(BaseModel):
    maps: list[int] = Field(default_factory=list, description="Map sets downloaded and handed to lazer.")
    failed: list[int] = Field(default_factory=list, description="Map sets that couldn't be downloaded.")
    not_found: int = Field(0, description="Maps you don't have whose beatmap set couldn't be found online.")
    imported: list[int] = Field(default_factory=list, description="Map sets lazer took (it deletes each .osz).")
    not_imported: list[int] = Field(
        default_factory=list,
        description="Map sets lazer hadn't taken when osu! coach stopped waiting: it may still be busy with them.",
    )


class LazerOpenRequest(Request):
    beatmap_id: int = Field(ge=1, le=2**31 - 1, description="The difficulty on the osu! website.")


class LazerOpened(BaseModel):
    link: str = Field(description="The link lazer was given, ``osu://b/<beatmap id>``.")


class StableMergeResult(BaseModel):
    path: str
    backup: str | None


class OszRequest(Request):
    folder: str = Field(min_length=1, max_length=1000)
    set_ids: list[int] = Field(min_length=1, max_length=10000)


class OszResult(BaseModel):
    folder: str
    downloaded: int
    failed: list[int]


class LazerSendJob(JobBase):
    kind: Literal["lazer_send"]
    result: LazerSendResult | None


class OszJob(JobBase):
    kind: Literal["osz_download"]
    result: OszResult | None

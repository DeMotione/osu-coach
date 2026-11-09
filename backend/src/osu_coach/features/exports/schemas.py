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
    lazer_sets: int = Field(description="Map sets the lazer import folder would download.")
    lazer_approximate: bool = Field(
        description="An upper bound: not all of lazer's files were read yet, or some maps' sets are only looked up "
        "when the folder is made."
    )
    lazer_folder: str = Field(description="The import folder for the collection (in osu! coach's data folder).")
    lazer_auto: bool = Field(
        description="lazer's program was found: the maps are handed straight to lazer instead of going into the folder."
    )
    stable_available: bool = Field(description="An osu!stable install to add the collection to was found.")
    osz_folder: str = Field(description="Default folder for .osz downloads (stable's Songs folder if found).")


class LazerPackResult(BaseModel):
    path: str
    maps: list[int]
    failed: list[int]
    not_found: int = Field(
        0,
        description="Maps you don't have whose beatmap set couldn't be found online: they are in the collection but "
        "not in the folder.",
    )
    sent_to_lazer: bool = Field(
        False, description="The maps were handed straight to lazer (``maps``), not put into the folder."
    )
    imported: list[int] = Field(default_factory=list, description="Map sets lazer took (it deletes each .osz).")
    not_imported: list[int] = Field(
        default_factory=list,
        description="Map sets lazer hadn't taken when osu! coach stopped waiting: it may still be busy with them.",
    )


class LazerFolderRequest(Request):
    name: str = Field(min_length=1, max_length=200, description="Collection name.")


class LazerFolderRemoved(BaseModel):
    path: str
    removed: bool


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


class LazerPackJob(JobBase):
    kind: Literal["lazer_pack"]
    result: LazerPackResult | None


class OszJob(JobBase):
    kind: Literal["osz_download"]
    result: OszResult | None

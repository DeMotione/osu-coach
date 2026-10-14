from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile

from osu_coach.app.deps import WorkspaceDep
from osu_coach.app.errors import ApiError, responses
from osu_coach.jobs.schemas import job_view
from osu_coach.library import service as svc
from osu_coach.library import uploads
from osu_coach.library.schemas import (
    InstallOut,
    LibraryOut,
    RescanRequest,
    ScanJob,
    ScanRequest,
    SelectionOut,
    UploadedFile,
)
from osu_coach.replays.schemas import DateRange, Latest

router = APIRouter(tags=["Replays"])


@router.get("/installs", summary="osu! installs found on this computer")
def installs(ws: WorkspaceDep, refresh: bool = False) -> list[InstallOut]:
    return [svc.install_out(i) for i in ws.installs(refresh=refresh)]


@router.post("/uploads", summary="Add replay (.osr) / beatmap (.osu) files", status_code=201, responses=responses(422))
def upload(
    files: Annotated[list[UploadFile], File(description=".osr replays and .osu beatmaps")], ws: WorkspaceDep
) -> list[UploadedFile]:
    return [uploads.save_upload(ws, f.filename or "upload", f.file.read(uploads.MAX_UPLOAD_BYTES + 1)) for f in files]


@router.post(
    "/library/scan", summary="Find replays (background job)", status_code=202, responses=responses(404, 409, 422)
)
def scan(req: ScanRequest, ws: WorkspaceDep) -> ScanJob:
    args = svc.scan_args(ws, req)
    if not args.only:
        ws.update_settings(source_mode=req.mode, latest=int(req.latest), folders="\n".join(req.folders))
    else:
        ws.update_settings(source_mode=req.mode)
    latest = 0 if args.only else int(req.latest)
    return job_view(
        ScanJob, ws.jobs.start("scan", "Scanning for replays", lambda report: svc.run_scan(ws, args, latest, report))
    )


@router.post(
    "/library/rescan",
    summary="Read the same sources further back (background job)",
    status_code=202,
    responses=responses(409),
)
def rescan(req: RescanRequest, ws: WorkspaceDep) -> ScanJob:
    """After choosing more replays than the last scan read (*Replays to read*), the same sources are scanned again."""
    lib = svc.require_library(ws)
    if ws.scan_args is None or ws.scan_args.only:
        raise ApiError(409, "nothing_to_rescan", "The last scan was of dropped files only.")
    latest = int(req.latest)
    if not svc.needs_more(lib, latest):
        raise ApiError(409, "nothing_to_rescan", "The last scan already read that many replays.")
    ws.update_settings(latest=latest)
    args = ws.scan_args
    return job_view(
        ScanJob, ws.jobs.start("scan", "Scanning for replays", lambda report: svc.run_scan(ws, args, latest, report))
    )


@router.get("/library", summary="What the last scan found")
def library(ws: WorkspaceDep) -> LibraryOut:
    return svc.library_out(ws)


@router.get("/library/selection", summary="Which replays an analysis would read", responses=responses(409, 422))
def selection(
    ws: WorkspaceDep,
    player: str | None = None,
    latest: Annotated[Latest, Query()] = Latest.newest_500,
    date_range: Annotated[DateRange, Query()] = "all",
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> SelectionOut:
    with ws.gate.hold("Checking the replays"):
        sel = svc.select(ws, player, int(latest), date_range, date_from, date_to)
        return svc.selection_out(ws, sel)

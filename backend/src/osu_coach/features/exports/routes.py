from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import Response

from osu_coach.app.deps import WorkspaceDep
from osu_coach.common.errors import responses
from osu_coach.common.jobs import job_view
from osu_coach.features.exports import service as svc
from osu_coach.features.exports.schemas import (
    ExportPreview,
    ExportRequest,
    LazerOpened,
    LazerOpenRequest,
    LazerSendJob,
    OszJob,
    OszRequest,
    StableMergeResult,
)

router = APIRouter(prefix="/exports", tags=["Get maps into osu!"])


def content_disposition(filename: str) -> str:
    """``attachment`` with an ASCII fallback name and the real (UTF-8) one (RFC 6266 / 5987): collection names
    carry a ★, which an HTTP header can't hold as it is."""
    fallback = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in filename)
    if fallback == filename:
        return f'attachment; filename="{filename}"'
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def _attachment(data: bytes, filename: str, media_type: str) -> Response:
    return Response(content=data, media_type=media_type, headers={"Content-Disposition": content_disposition(filename)})


@router.post("/preview", summary="What each way of getting these maps would do")
def preview(req: ExportRequest, ws: WorkspaceDep) -> ExportPreview:
    return svc.export_preview(ws, req)


@router.post(
    "/collection-db",
    summary="collection.db with these maps",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
def collection_db(req: ExportRequest) -> Response:
    return _attachment(svc.collection_db(req), "collection.db", "application/octet-stream")


@router.post(
    "/lazer-send",
    summary="Send the maps to osu!lazer (background job)",
    status_code=202,
    responses=responses(404, 409),
)
def lazer_send(req: ExportRequest, ws: WorkspaceDep) -> LazerSendJob:
    """The maps lazer doesn't have yet are downloaded into osu! coach's data folder (``lazer-maps``) and handed to
    lazer, which imports them and deletes the files (it starts if it's closed). 404 ``no_lazer`` without lazer."""
    exe = svc.lazer_program()  # refused before a job starts
    return job_view(
        LazerSendJob,
        ws.jobs.start(
            "lazer_send",
            "Sending the maps to lazer",
            lambda report: svc.send_to_lazer(ws, req, report, exe),
            cancellable=True,
        ),
    )


@router.post("/lazer-open", summary="Open a map in osu!lazer", responses=responses(404))
def lazer_open(req: LazerOpenRequest) -> LazerOpened:
    """Shows the map's page in lazer with this difficulty picked (lazer starts if it's closed); lazer's "Go to
    beatmap" button there jumps to it in song select. 404 ``no_lazer`` without lazer."""
    return svc.open_in_lazer(req.beatmap_id)


@router.post("/stable-collection", summary="Add the collection to osu!stable", responses=responses(404, 409))
def stable_collection(req: ExportRequest, ws: WorkspaceDep) -> StableMergeResult:
    """osu! must be closed; the old collection.db is backed up first."""
    return svc.merge_stable(ws, req)


@router.post(
    "/osz", summary="Download the maps (.osz) into a folder (background job)", status_code=202, responses=responses(422)
)
def osz(req: OszRequest, ws: WorkspaceDep) -> OszJob:
    sets = svc.known_sets(req.set_ids)  # refused before a job starts
    return job_view(
        OszJob,
        ws.jobs.start(
            "osz_download",
            "Downloading maps",
            lambda report: svc.download_osz(req.folder, sets, report),
            exclusive=False,
            cancellable=True,
        ),
    )

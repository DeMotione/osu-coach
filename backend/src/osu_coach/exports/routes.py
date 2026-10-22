from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import Response

from osu_coach.app.deps import WorkspaceDep
from osu_coach.app.errors import responses
from osu_coach.exports import service as svc
from osu_coach.exports.schemas import ExportPreview, ExportRequest, LazerPackJob, OszJob, OszRequest, StableMergeResult
from osu_coach.jobs.schemas import job_view

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
    "/lazer-zip",
    summary="lazer import folder without maps (.zip)",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)
def lazer_zip(req: ExportRequest) -> Response:
    """Just the collection, e.g. for lazer on another computer: unzip it and import the folder."""
    data, name = svc.lazer_zip(req)
    return _attachment(data, name, "application/zip")


@router.post(
    "/lazer-pack", summary="Make the lazer import folder (background job)", status_code=202, responses=responses(409)
)
def lazer_pack(req: ExportRequest, ws: WorkspaceDep) -> LazerPackJob:
    """In Downloads/osu-coach lazer import/<name>: the collection plus the maps lazer doesn't have yet."""
    return job_view(
        LazerPackJob,
        ws.jobs.start(
            "lazer_pack",
            "Making the lazer import folder",
            lambda report: svc.build_lazer_pack(ws, req, report),
            cancellable=True,
        ),
    )


@router.post("/stable-collection", summary="Add the collection to osu!stable", responses=responses(404, 409))
def stable_collection(req: ExportRequest, ws: WorkspaceDep) -> StableMergeResult:
    """osu! must be closed; the old collection.db is backed up first."""
    return svc.merge_stable(ws, req)


@router.post(
    "/osz", summary="Download the maps (.osz) into a folder (background job)", status_code=202, responses=responses(422)
)
def osz(req: OszRequest, ws: WorkspaceDep) -> OszJob:
    return job_view(
        OszJob,
        ws.jobs.start(
            "osz_download",
            "Downloading maps",
            lambda report: svc.download_osz(req.folder, req.set_ids, report),
            exclusive=False,
            cancellable=True,
        ),
    )

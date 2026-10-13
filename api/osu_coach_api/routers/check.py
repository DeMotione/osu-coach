from __future__ import annotations

from fastapi import APIRouter

from ..deps import WorkspaceDep
from ..errors import responses
from ..schemas.check import CheckList, CheckReport, CheckRequest
from ..services import check as svc

router = APIRouter(prefix="/check", tags=["Detailed Map Analysis"])


@router.get("/replays", summary="Replays to check (newest first)", responses=responses(404, 409, 422))
def replays(ws: WorkspaceDep, path: str | None = None, only_map: bool = False) -> CheckList:
    """Without a scan, the newest replays of the osu! installs on this computer are read. ``path``: a replay opened
    from another page or uploaded (always listed); ``only_map``: only the plays of that replay's map."""
    return svc.replay_list(ws, path, only_map)


@router.post("/report", summary="Check one replay", responses=responses(404, 409, 422))
def report(req: CheckRequest, ws: WorkspaceDep) -> CheckReport:
    """Every miss and combo break with its map time, where they cluster, the timing through the map and how the play
    compares with your other plays of the map. The play is saved in the progress history."""
    return svc.report(ws, req.path, req.online)

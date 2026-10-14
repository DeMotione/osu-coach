from __future__ import annotations

from typing import TYPE_CHECKING

import datetime as dt

from fastapi import APIRouter
from pydantic import ValidationError

from osu_coach.settings.domain import Setup

from osu_coach.app.deps import WorkspaceDep
from osu_coach.app.errors import responses
from osu_coach.settings.schemas import AppSettings, SettingsPatch, SetupModel, SetupUpdate
from osu_coach.settings.service import default_folders, setup_model

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace

router = APIRouter(tags=["Settings"])
NULLABLE = {"date_from", "date_to", "level_override", "player"}   # null clears these


def _date(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(v) if v else None
    except (TypeError, ValueError):
        return None


def app_settings(ws: Workspace) -> AppSettings:
    """The stored settings; a value the app doesn't know (an older or hand-edited file) falls back to its default."""
    s = ws.settings()
    raw = {"source_mode": s.get("source_mode"), "folders": default_folders(s), "latest": s.get("latest"),
           "date_range": s.get("date_range"), "date_from": _date(s.get("date_from")), "date_to": _date(s.get("date_to")),
           "replay_set": s.get("replay_set"), "level_override": s.get("level_override"), "player": s.get("player"),
           "manual_comfort": s.get("manual_comfort"), "setup_saved": bool(s.get("setup_saved"))}
    out = {}
    for k, v in raw.items():
        if v is None:
            continue
        try:
            AppSettings.model_validate({k: v})
        except ValidationError:
            continue
        out[k] = v
    return AppSettings.model_validate(out)


@router.get("/settings", summary="Remembered choices")
def get_settings(ws: WorkspaceDep) -> AppSettings:
    return app_settings(ws)


@router.patch("/settings", summary="Change remembered choices", responses=responses(422))
def patch_settings(patch: SettingsPatch, ws: WorkspaceDep) -> AppSettings:
    changes = {k: v for k, v in patch.model_dump(exclude_unset=True, mode="json").items()
               if v is not None or k in NULLABLE}
    if changes:
        ws.update_settings(**changes)
    return app_settings(ws)


@router.get("/setup", summary="Your setup (aim device, keys)")
def get_setup(ws: WorkspaceDep) -> SetupModel:
    return setup_model(ws.setup())


@router.put("/setup", summary="Save your setup", responses=responses(422))
def put_setup(setup: SetupUpdate, ws: WorkspaceDep) -> SetupModel:
    values = setup.model_dump()
    ws.update_settings(setup_saved=True, **{k: v for k, v in values.items() if k in Setup.__dataclass_fields__})
    return setup_model(ws.setup())

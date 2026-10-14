from __future__ import annotations

from fastapi import APIRouter

from osu_coach.app.deps import WorkspaceDep
from osu_coach.app.errors import responses
from osu_coach.settings.domain import Setup
from osu_coach.settings.schemas import AppSettings, SettingsPatch, SetupModel, SetupUpdate
from osu_coach.settings.service import NULLABLE, app_settings, setup_model

router = APIRouter(tags=["Settings"])


@router.get("/settings", summary="Remembered choices")
def get_settings(ws: WorkspaceDep) -> AppSettings:
    return app_settings(ws)


@router.patch("/settings", summary="Change remembered choices", responses=responses(422))
def patch_settings(patch: SettingsPatch, ws: WorkspaceDep) -> AppSettings:
    changes = {
        k: v for k, v in patch.model_dump(exclude_unset=True, mode="json").items() if v is not None or k in NULLABLE
    }
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

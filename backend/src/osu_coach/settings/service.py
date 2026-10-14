"""The remembered choices and the player's setup as the API shows them."""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import asdict
from typing import TYPE_CHECKING

from pydantic import ValidationError

from osu_coach.settings.domain import Setup
from osu_coach.settings.schemas import AppSettings, SetupModel

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace


# ------------------------------------------------------------------ tips & setup
def setup_model(setup: Setup) -> SetupModel:
    try:
        return SetupModel.model_validate(asdict(setup))
    except ValidationError:     # a value out of range in an old settings file: shown as it is
        return SetupModel.model_construct(**asdict(setup))


def default_folders(settings: dict) -> str:
    return settings.get("folders") or os.environ.get("OSU_COACH_DEMO", "")


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

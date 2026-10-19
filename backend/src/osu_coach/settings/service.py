"""The remembered choices and the player's setup as the API shows them."""

from __future__ import annotations

import datetime as dt
import logging
import os
from dataclasses import asdict
from typing import TYPE_CHECKING

from pydantic import ValidationError

from osu_coach.settings.domain import Setup
from osu_coach.settings.schemas import AppSettings, SetupModel

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace

log = logging.getLogger("osu_coach.settings.service")


# ------------------------------------------------------------------ tips & setup
def setup_model(setup: Setup) -> SetupModel:
    try:
        return SetupModel.model_validate(asdict(setup))
    except ValidationError:  # a value out of range in an old settings file: shown as it is
        return SetupModel.model_construct(**asdict(setup))


def default_folders(settings: dict) -> str:
    return settings.get("folders") or os.environ.get("OSU_COACH_DEMO", "")


NULLABLE = {"date_from", "date_to", "level_override", "player"}  # null clears these


def _date(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(v) if v else None
    except (TypeError, ValueError):
        return None


def app_settings(ws: Workspace) -> AppSettings:
    """The stored settings; a value the app doesn't know (an older or hand-edited file) falls back to its default."""
    s = ws.settings()
    raw = {
        "source_mode": s.get("source_mode"),
        "folders": default_folders(s),
        "latest": s.get("latest"),
        "date_range": s.get("date_range"),
        "date_from": _date(s.get("date_from")),
        "date_to": _date(s.get("date_to")),
        "replay_set": s.get("replay_set"),
        "level_override": s.get("level_override"),
        "player": s.get("player"),
        "manual_comfort": s.get("manual_comfort"),
        "setup_saved": bool(s.get("setup_saved")),
        "onboarded": bool(s.get("onboarded")),
    }
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


def settle_onboarding(ws: Workspace) -> None:
    """Whether the setup guide is still to come, written down at the first start: a new data folder gets the guide;
    settings saved by a version without it (or by the command line) mean osu! coach is set up already. Settings
    saved during the guide (the setup) don't count, as the flag is in the file by then."""
    s = ws.settings()
    if "onboarded" in s:
        return
    try:
        ws.update_settings(onboarded=bool(s))
    except OSError:  # a data folder that can't be written: the guide shows, and asks again next time
        log.warning("could not save settings.json", exc_info=True)

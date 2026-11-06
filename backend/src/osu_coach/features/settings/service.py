"""The remembered choices and the player's setup as the API shows them."""

from __future__ import annotations

import datetime as dt
import logging
import os
from typing import TYPE_CHECKING

from pydantic import ValidationError

from osu_coach.features.settings.schemas import AppSettings

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace
    from osu_coach.infra.settings import UserSettings

log = logging.getLogger("osu_coach.features.settings.service")


def default_folders(settings: UserSettings) -> str:
    return settings.folders or os.environ.get("OSU_COACH_DEMO", "")


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
        "source_mode": s.source_mode,
        "folders": default_folders(s),
        "latest": s.latest,
        "date_range": s.date_range,
        "date_from": _date(s.date_from),
        "date_to": _date(s.date_to),
        "replay_set": s.replay_set,
        "level_override": s.level_override,
        "player": s.player,
        "manual_comfort": s.manual_comfort,
        "setup_saved": bool(s.setup_saved),
        "onboarded": bool(s.onboarded),
        "auto_analyse": s.auto_analyse,
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
    if "onboarded" in s.values:
        return
    try:
        ws.update_settings(onboarded=bool(s.values))
    except OSError:  # a data folder that can't be written: the guide shows, and asks again next time
        log.warning("could not save settings.json", exc_info=True)

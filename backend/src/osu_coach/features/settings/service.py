"""The remembered choices and the player's setup as the API shows them."""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging
import os
from typing import TYPE_CHECKING

from pydantic import ValidationError

from osu_coach.domain.player.setup import Setup, changed_groups
from osu_coach.domain.replays.selection import MOST_REPLAYS
from osu_coach.features.settings.schemas import AppSettings
from osu_coach.infra import clock

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace
    from osu_coach.infra.settings import UserSettings

log = logging.getLogger("osu_coach.features.settings.service")


def save_setup(ws: Workspace, values: dict) -> None:
    """Save the setup. The groups of settings this save changes (:func:`changed_groups`) are stamped with the time,
    so their Setup Tips wait for plays made with the new values (#131); the first save describes the setup and
    changes nothing."""
    s = ws.settings()
    entered = {k: v for k, v in values.items() if k in Setup.__dataclass_fields__}
    before = ws.setup()
    changed = changed_groups(before, dataclasses.replace(before, **entered)) if s.setup_saved else set()
    now = clock.now().isoformat()
    stamps = {g: t.isoformat() for g, t in s.setup_changed.items()} | dict.fromkeys(changed, now)
    ws.update_settings(setup_saved=True, setup_changed=stamps, **entered)


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
        "latest": MOST_REPLAYS if s.latest == 0 else s.latest,  # "all", no longer offered: the most there is
        "date_range": s.date_range,
        "date_from": _date(s.date_from),
        "date_to": _date(s.date_to),
        "replay_set": s.replay_set,
        "rating_engine": s.rating_engine,
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

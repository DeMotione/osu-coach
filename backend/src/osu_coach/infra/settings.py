"""``settings.json`` in the data folder: the user's goals, hidden maps, setup and remembered choices."""

from __future__ import annotations

import datetime as dt
import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from osu_coach.config import default_cache_dir


def load_settings(cache_dir=None) -> dict:
    try:
        settings = json.loads((Path(cache_dir or default_cache_dir()) / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return settings if isinstance(settings, dict) else {}


def save_settings(settings: dict, cache_dir=None) -> None:
    p = Path(cache_dir or default_cache_dir())
    p.mkdir(parents=True, exist_ok=True)
    # written beside the file and swapped in, so a crash mid-write can't leave a truncated settings.json behind
    tmp = p / "settings.json.tmp"
    tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    os.replace(tmp, p / "settings.json")


# the type checks: settings.json can be edited by hand, so a value that isn't of the setting's type reads as
# missing. Pydantic's lax mode, as the settings page always checked them: 100.0 is an int, 1 and "true" are True.
_STR, _BOOL, _INT, _FLOAT = TypeAdapter(str), TypeAdapter(bool), TypeAdapter(int), TypeAdapter(float)


def _lax(adapter: TypeAdapter, v: object):
    if v is None:
        return None
    try:
        return adapter.validate_python(v)
    except ValidationError:
        return None


def _str(v: object) -> str | None:
    return _lax(_STR, v)


def _bool(v: object) -> bool | None:
    return _lax(_BOOL, v)


def _int(v: object) -> int | None:
    return None if isinstance(v, bool) else _lax(_INT, v)


def _float(v: object) -> float | None:
    f = None if isinstance(v, bool) else _lax(_FLOAT, v)
    return f if f is not None and math.isfinite(f) else None


def _strs(v: object) -> list[str] | None:
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else None


def _iso_date(v: object) -> bool:
    if not isinstance(v, str):
        return False
    try:
        dt.date.fromisoformat(v)
    except ValueError:
        return False
    return True


def _usable_goal(g: object) -> bool:
    """A saved progress goal with what the goal pages read from it."""
    return (
        isinstance(g, dict)
        and isinstance(g.get("id"), str)
        and isinstance(g.get("skill"), str)
        and _float(g.get("target")) is not None
        and _iso_date(g.get("created"))
        and _iso_date(g.get("deadline"))
        and (not g.get("done") or _iso_date(g.get("done")))
    )


@dataclass(frozen=True)
class UserSettings:
    """``settings.json`` as read: each known setting as a typed property, None when it isn't there or has the wrong
    type (the file can be edited by hand); the readers check the allowed values. ``values`` keeps the whole file as
    it is, keys of other versions included; changes go through :func:`save_settings` (``Workspace.update_settings``),
    which keeps every other key."""

    values: Mapping[str, Any] = field(default_factory=dict)

    # what to read and analyse
    @property
    def source_mode(self) -> str | None:
        """Library | folders | files."""
        return _str(self.values.get("source_mode"))

    @property
    def folders(self) -> str | None:
        """Extra replay folders, one per line."""
        return _str(self.values.get("folders"))

    @property
    def install_paths(self) -> list[str] | None:
        """Osu! folders the player entered."""
        return _strs(self.values.get("install_paths"))

    @property
    def latest(self) -> int | None:
        """The newest replays to analyse; 0 = all."""
        return _int(self.values.get("latest"))

    @property
    def date_range(self) -> str | None:
        """The time range to analyse."""
        return _str(self.values.get("date_range"))

    @property
    def date_from(self) -> str | None:
        """ISO date."""
        return _str(self.values.get("date_from"))

    @property
    def date_to(self) -> str | None:
        """ISO date."""
        return _str(self.values.get("date_to"))

    @property
    def player(self) -> str | None:
        """The player analysed last; '*' = all players."""
        return _str(self.values.get("player"))

    @property
    def replay_set(self) -> str | None:
        """All | best."""
        return _str(self.values.get("replay_set"))

    @property
    def rating_engine(self) -> str | None:
        """Classic | irt: the engine that makes the skill ratings."""
        return _str(self.values.get("rating_engine"))

    @property
    def level_override(self) -> float | None:
        """The level (★) set by hand."""
        return _float(self.values.get("level_override"))

    @property
    def manual_comfort(self) -> float | None:
        """Star rating for playlists without analysed replays."""
        return _float(self.values.get("manual_comfort"))

    @property
    def auto_analyse(self) -> bool | None:
        """Analyse new plays by themselves."""
        return _bool(self.values.get("auto_analyse"))

    # the setup and the first start
    @property
    def client(self) -> str | None:
        """Stable | lazer."""
        return _str(self.values.get("client"))

    @property
    def setup_saved(self) -> bool | None:
        """The setup was saved by the player."""
        return _bool(self.values.get("setup_saved"))

    @property
    def onboarded(self) -> bool | None:
        """The first-start guide was finished or skipped."""
        return _bool(self.values.get("onboarded"))

    # what the pages remember
    @property
    def hidden_maps(self) -> list[str] | None:
        """Md5s of maps hidden from the suggestions."""
        return _strs(self.values.get("hidden_maps"))

    @property
    def goals(self) -> list[dict] | None:
        """The progress goals (dicts); a goal the pages couldn't read is left out (see :attr:`unreadable_goals`)."""
        gl = self.values.get("goals")
        return [g for g in gl if _usable_goal(g)] if isinstance(gl, list) else None

    @property
    def unreadable_goals(self) -> list:
        """The saved goals left out of :attr:`goals`, to be saved back as they are (a hand edit to fix, not lose)."""
        gl = self.values.get("goals")
        return [g for g in gl if not _usable_goal(g)] if isinstance(gl, list) else []

    @property
    def play_goal_request(self) -> dict | None:
        """The last play-goal request."""
        v = self.values.get("play_goal_request")
        return v if isinstance(v, dict) else None


def read_settings(cache_dir=None) -> UserSettings:
    return UserSettings(load_settings(cache_dir))

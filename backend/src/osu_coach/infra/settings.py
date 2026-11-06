"""``settings.json`` in the data folder: the user's goals, hidden maps, setup and remembered choices."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


@dataclass(frozen=True)
class UserSettings:
    """``settings.json`` as read: each known setting as a typed property (exactly what the file holds, None when it
    isn't there; the readers check the values). ``values`` keeps the whole file, keys of other versions included;
    changes go through :func:`save_settings` (``Workspace.update_settings``), which keeps every other key."""

    values: Mapping[str, Any] = field(default_factory=dict)

    # what to read and analyse
    @property
    def source_mode(self) -> str | None:
        """Library | folders | files."""
        return self.values.get("source_mode")

    @property
    def folders(self) -> str | None:
        """Extra replay folders, one per line."""
        return self.values.get("folders")

    @property
    def install_paths(self) -> list | None:
        """Osu! folders the player entered."""
        return self.values.get("install_paths")

    @property
    def latest(self) -> int | None:
        """The newest replays to analyse; 0 = all."""
        return self.values.get("latest")

    @property
    def date_range(self) -> str | None:
        """The time range to analyse."""
        return self.values.get("date_range")

    @property
    def date_from(self) -> str | None:
        """ISO date."""
        return self.values.get("date_from")

    @property
    def date_to(self) -> str | None:
        """ISO date."""
        return self.values.get("date_to")

    @property
    def player(self) -> str | None:
        """The player analysed last; '*' = all players."""
        return self.values.get("player")

    @property
    def replay_set(self) -> str | None:
        """All | best."""
        return self.values.get("replay_set")

    @property
    def level_override(self) -> float | None:
        """The level (★) set by hand."""
        return self.values.get("level_override")

    @property
    def manual_comfort(self) -> float | None:
        """Star rating for playlists without analysed replays."""
        return self.values.get("manual_comfort")

    @property
    def auto_analyse(self) -> bool | None:
        """Analyse new plays by themselves."""
        return self.values.get("auto_analyse")

    # the setup and the first start
    @property
    def client(self) -> str | None:
        """Stable | lazer."""
        return self.values.get("client")

    @property
    def setup_saved(self) -> bool | None:
        """The setup was saved by the player."""
        return self.values.get("setup_saved")

    @property
    def onboarded(self) -> bool | None:
        """The first-start guide was finished or skipped."""
        return self.values.get("onboarded")

    # what the pages remember
    @property
    def hidden_maps(self) -> list | None:
        """Md5s of maps hidden from the suggestions."""
        return self.values.get("hidden_maps")

    @property
    def goals(self) -> list | None:
        """The progress goals (dicts)."""
        return self.values.get("goals")

    @property
    def play_goal_request(self) -> dict | None:
        """The last play-goal request."""
        return self.values.get("play_goal_request")


def read_settings(cache_dir=None) -> UserSettings:
    return UserSettings(load_settings(cache_dir))

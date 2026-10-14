"""``settings.json`` in the data folder: the user's goals, hidden maps, setup and remembered choices."""

from __future__ import annotations

import json
import os
from pathlib import Path

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

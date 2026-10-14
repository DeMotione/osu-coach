"""``settings.json`` in the data folder: the user's goals, hidden maps, setup and remembered choices."""

from __future__ import annotations

import json
from pathlib import Path

from osu_coach.config import default_cache_dir


def load_settings(cache_dir=None) -> dict:
    try:
        return json.loads((Path(cache_dir or default_cache_dir()) / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict, cache_dir=None) -> None:
    p = Path(cache_dir or default_cache_dir())
    p.mkdir(parents=True, exist_ok=True)
    (p / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")

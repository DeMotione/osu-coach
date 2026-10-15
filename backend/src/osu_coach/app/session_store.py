"""``session.json`` in the data folder: what the last scan read and which replays were analysed, so the next
start can pick up where this one stopped (see :func:`osu_coach.app.session.restore`)."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

FILE = "session.json"
_lock = threading.Lock()


def load(cache_dir: Path) -> dict:
    try:
        data = json.loads((cache_dir / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def update(cache_dir: Path, **sections: dict) -> None:
    """Replace the given sections (``scan`` / ``analysis``), keeping the others."""
    with _lock:
        data = load(cache_dir)
        data.update(sections)
        # written beside the file and swapped in, so a crash mid-write can't leave a truncated file behind
        tmp = cache_dir / f"{FILE}.tmp"
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, cache_dir / FILE)

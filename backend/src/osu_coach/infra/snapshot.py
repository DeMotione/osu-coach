"""``snapshot.json.gz`` in the data folder: the Analysis pages of the last completed analysis, as they were answered
(#97). At the next start they are shown at once, while the analysed plays come back and the last scan runs again in
the background (:func:`osu_coach.features.library.session.start_restore`).

A snapshot is of one version of the code (``version``, given by the caller: pages of another version may not fit the
web app) and of the choices that made its profile (``selection``: the analysed plays, All / Best replays, the level,
the rating engine, the setup); it is shown only when both are the same again.
"""

from __future__ import annotations

import gzip
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FILE = "snapshot.json.gz"
FORMAT = 1
_lock = threading.Lock()


@dataclass
class Snapshot:
    selection: dict[str, Any]
    analysed_at: str  # when the analysis behind it ended (ISO 8601 UTC)
    pages: dict[str, Any] = field(default_factory=dict)  # request path with its query: the answer's body


def load(cache_dir: Path, version: str) -> Snapshot | None:
    """The snapshot saved by this version of the code, or None."""
    try:
        with gzip.open(cache_dir / FILE, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, EOFError):
        return None
    if not isinstance(data, dict) or data.get("format") != FORMAT or data.get("version") != version:
        return None
    selection, at, pages = data.get("selection"), data.get("analysed_at"), data.get("pages")
    if not isinstance(selection, dict) or not isinstance(at, str) or not isinstance(pages, dict):
        return None
    return Snapshot(selection, at, pages)


def save(cache_dir: Path, version: str, snapshot: Snapshot) -> None:
    data = {
        "format": FORMAT,
        "version": version,
        "selection": snapshot.selection,
        "analysed_at": snapshot.analysed_at,
        "pages": snapshot.pages,
    }
    with _lock:
        # written beside the file and swapped in, so a crash mid-write can't leave a truncated file behind
        tmp = cache_dir / f"{FILE}.tmp"
        with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=1) as fh:
            json.dump(data, fh, separators=(",", ":"))
        os.replace(tmp, cache_dir / FILE)

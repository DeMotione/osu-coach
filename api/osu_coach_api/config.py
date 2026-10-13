"""Runtime configuration of the API."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

# The app reads and writes files on this computer, so it only answers to the computer itself: requests
# for any other host name (DNS rebinding) are refused.
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
DEFAULT_PORT = 8501


@dataclass(frozen=True)
class ApiConfig:
    cache_dir: Path | None = None
    """osu! coach data folder (settings, analysis cache, progress); None = the domain's default
    (``OSU_COACH_CACHE`` or the per-user cache folder)."""
    web_dir: Path | None = None
    """Built web app to serve at ``/``; None = :func:`find_web_dir`."""
    allowed_hosts: tuple[str, ...] = LOCAL_HOSTS
    """Host names the API answers to (without port)."""
    reveal_folders: bool = True
    """Open the file manager on folders the app creates (lazer import folder)."""
    analysis_workers: int | None = None
    """Processes for replay analysis; None = the domain's default (CPU count − 1, at most 8)."""


def find_web_dir() -> Path | None:
    """The built web app: ``OSU_COACH_WEB_DIR``, the copy bundled into the package / the installed .exe, or
    ``frontend/dist`` of a source checkout."""
    candidates = []
    if os.environ.get("OSU_COACH_WEB_DIR"):
        candidates.append(Path(os.environ["OSU_COACH_WEB_DIR"]))
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "osu_coach_api" / "web")
    here = Path(__file__).resolve().parent
    candidates += [here / "web", here.parents[1] / "frontend" / "dist"]
    return next((c for c in candidates if (c / "index.html").is_file()), None)

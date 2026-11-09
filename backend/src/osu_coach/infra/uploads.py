"""Files the user adds in the web app (replays and beatmaps), kept in the data folder's ``uploads`` folder."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from osu_coach.common.errors import ApiError, Invalid

if TYPE_CHECKING:
    from osu_coach.infra.library import Library

UPLOAD_SUFFIXES = {".osr": "replay", ".osu": "beatmap"}
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
# names Windows keeps for devices, with any extension ("NUL.osr" is the NUL device, not a file)
DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"{kind}{i}" for kind in ("COM", "LPT") for i in range(1, 10)}


def uploads_dir(cache_dir: Path) -> Path:
    d = Path(cache_dir) / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_upload_name(name: str) -> str:
    """The file name without folders, characters file systems reject or a Windows device name."""
    base = Path(name.replace("\\", "/")).name
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", base)[:180].strip(" .")
    if base.split(".")[0].strip().upper() in DEVICE_NAMES:
        base = "_" + base
    return base or "upload"


def find_upload(cache_dir: Path, name: str) -> Path | None:
    """The file in the uploads folder called ``name`` (as :func:`safe_upload_name` makes it), or None. The path is
    taken from the folder's own listing, never built from ``name``, so it can't point anywhere else."""
    wanted = safe_upload_name(name)
    return next((p for p in uploads_dir(cache_dir).iterdir() if p.name == wanted and p.is_file()), None)


def upload_target(cache_dir: Path, name: str) -> Path:
    """Where an uploaded file called ``name`` is saved: directly inside the uploads folder."""
    folder = uploads_dir(cache_dir)
    dest = folder / safe_upload_name(name)
    if dest.resolve().parent != folder.resolve():
        raise Invalid(f"{name}: not a usable file name.", "bad_upload_name")
    return dest


def same_file(a, b) -> bool:
    """Whether two paths name the same file (False for a value that is no path)."""
    try:
        return Path(a) == Path(b)
    except TypeError:
        return False


def known_replay(path: str, cache_dir: Path, libraries: Iterable[Library | None]) -> Path:
    """The replay file a request names: only one a library already knows (lazer's are in its file store, named
    without .osr) or an .osr in the uploads folder (the API hands out those paths itself), never an arbitrary
    location. The returned path comes from there, not from the request."""
    wanted = Path(path)
    known = next(
        (Path(r["path"]) for lib in libraries if lib is not None for r in lib.replays if same_file(r["path"], wanted)),
        None,
    )
    if known is None:
        if wanted.suffix.lower() != ".osr":
            raise Invalid("Not a replay file (.osr).", "not_a_replay")
        uploaded = find_upload(cache_dir, wanted.name)
        known = uploaded if uploaded is not None and same_file(uploaded, wanted) else None
    if known is None or not known.is_file():
        raise ApiError(404, "replay_not_found", "The replay file is no longer on this computer.")
    return known

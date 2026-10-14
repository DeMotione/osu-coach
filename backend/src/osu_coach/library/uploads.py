"""Files the user adds in the web app (replays and beatmaps), kept in the data folder's ``uploads`` folder."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from osu_coach.app.errors import Invalid, NotFound
from osu_coach.library.schemas import UploadedFile

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace


UPLOAD_SUFFIXES = {".osr": "replay", ".osu": "beatmap"}
MAX_UPLOAD_BYTES = 64 * 1024 * 1024


def uploads_dir(ws: Workspace) -> Path:
    d = ws.cache_dir / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_upload_name(name: str) -> str:
    """The file name without folders or characters file systems reject."""
    base = Path(name.replace("\\", "/")).name
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", base).strip(" .")
    return base[:180] or "upload"


def save_upload(ws: Workspace, name: str, data: bytes) -> UploadedFile:
    clean = safe_upload_name(name)
    kind = UPLOAD_SUFFIXES.get(Path(clean).suffix.lower())
    if kind is None:
        raise Invalid(f"{name}: only .osr replays and .osu beatmaps can be added.", "unsupported_file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise Invalid(f"{name}: file too large.", "file_too_large")
    dest = uploads_dir(ws) / clean
    dest.write_bytes(data)
    return UploadedFile(id=clean, name=name, path=str(dest), kind=kind, size=len(data))


def resolve_upload(ws: Workspace, upload_id: str) -> Path:
    """An uploaded file by its id; only files inside the uploads folder."""
    p = uploads_dir(ws) / safe_upload_name(upload_id)
    if not p.is_file():
        raise NotFound(f"Uploaded file {upload_id} not found — add it again.", "upload_not_found")
    return p

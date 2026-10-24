"""Get a playlist into osu!lazer with a single import.

lazer has no file import for collections. Its "import from a previous osu! version"
(Settings → General → Run setup wizard → Import) accepts any folder that looks like an
osu!stable install — one with an ``osu!.*.cfg`` file or a ``Songs`` folder — imports the
beatmap folders inside ``Songs`` first and ``collection.db`` after that.  So one prepared
folder brings the playlist's maps *and* its collection in together:

    <folder>/osu!.user.cfg     empty, marks the folder as a stable install
    <folder>/collection.db     the playlist
    <folder>/Songs/<set id>/   maps you don't have yet, unpacked from their .osz
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import zipfile
from contextlib import closing
from pathlib import Path

from osu_coach.beatmaps import sources
from osu_coach.exports.collection_db import dumps, write_collection_db

STABLE_MARKER = "osu!.user.cfg"


def safe_name(name: str) -> str:
    """A folder name without characters Windows forbids and without dots: lazer routes a
    dropped path by its extension, and only an extension-less folder reaches the import screen."""
    s = re.sub(r'[\\/:*?"<>|]+', " ", str(name)).replace(".", ",").strip()
    return re.sub(r"\s+", " ", s)[:80].strip() or "osu-coach playlist"


def default_pack_dir(name: str) -> Path:
    """A visible place (lazer's folder picker hides hidden folders such as AppData):
    ``Downloads/osu-coach lazer import/<playlist>``, or the home folder without Downloads."""
    home = Path.home()
    base = home / "Downloads" if (home / "Downloads").is_dir() else home
    return base / "osu-coach lazer import" / safe_name(name)


def _extract_osz(osz: Path, target: Path) -> Path:
    """Unpack an .osz (a zip) into ``target``, skipping entries that would land outside it."""
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    with zipfile.ZipFile(osz) as z:
        for info in z.infolist():
            out = (target / info.filename).resolve()
            if root not in out.parents:
                continue
            if info.is_dir():
                out.mkdir(parents=True, exist_ok=True)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
    return target


def _has_maps(folder: Path) -> bool:
    return folder.is_dir() and any(folder.glob("*.osu"))


def build_pack(dest, collections: dict, sets=(), progress=None, download=None) -> dict:
    """Write the import folder.

    ``collections``: {name: [beatmap md5, ...]}; ``sets``: beatmapset ids to put into
    ``Songs/<set id>/`` (downloaded as .osz, unpacked, the .osz deleted again; sets already
    there from an earlier run are kept), a few downloads at a time (:func:`sources.download_many`).
    ``download(set_id, dir) -> Path | None`` replaces :func:`sources.download_osz`.
    Returns {"path", "maps": [set ids], "failed": [set ids]}, each in the order of ``sets``."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / STABLE_MARKER).write_text("", encoding="utf-8")
    write_collection_db(dest / "collection.db", collections)
    songs = dest / "Songs"
    songs.mkdir(exist_ok=True)
    fetch = (lambda sid, folder, stop: download(sid, folder)) if download else None
    tmp = dest / "_downloading"
    sets = list(dict.fromkeys(int(s) for s in sets))
    # short paths (Songs/<set id>): Windows' 260-character limit
    got = [sid for sid in sets if _has_maps(songs / str(sid))]
    failed = []
    # ``progress`` raises to stop a cancelled job: the sets done so far stay for the next run
    try:
        with closing(sources.download_many([s for s in sets if s not in got], tmp, progress, download=fetch)) as done:
            for sid, osz in done:
                target = songs / str(sid)
                if not osz:
                    failed.append(sid)
                    continue
                try:
                    _extract_osz(Path(osz), target)
                except (zipfile.BadZipFile, OSError):
                    shutil.rmtree(target, ignore_errors=True)
                    failed.append(sid)
                    continue
                finally:
                    Path(osz).unlink(missing_ok=True)
                (got if _has_maps(target) else failed).append(sid)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    got.sort(key=sets.index)
    failed.sort(key=sets.index)
    if progress and sets:
        progress(len(sets), len(sets), "Done")
    return {"path": dest, "maps": got, "failed": failed}


def pack_zip(collections: dict, name: str) -> bytes:
    """The same folder as a .zip, without maps (for a lazer on another computer)."""
    folder = safe_name(name)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{folder}/{STABLE_MARKER}", "")
        z.writestr(f"{folder}/collection.db", dumps(collections))
    return buf.getvalue()


def reveal(path) -> bool:
    """Show the folder in the file manager (selected, where supported). Best effort."""
    path = Path(path)
    try:
        if os.name == "nt":
            subprocess.Popen(["explorer", f"/select,{path}"])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
        return True
    except OSError:
        return False


INSTRUCTIONS = [
    "In osu!lazer open **Settings → General → Run setup wizard** and press **Next** until the **Import** step.",
    "Drag the folder onto the lazer window (or click the *previous osu! install* box and pick the folder).",
    "Press **Import content from previous version**. Maps and the collection show up in song select; the "
    "folder can be deleted afterwards.",
]

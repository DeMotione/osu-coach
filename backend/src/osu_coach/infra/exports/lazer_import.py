"""Get a playlist into osu!lazer.

Maps go in by themselves: lazer imports an .osz passed to its program (``osu!.exe <file.osz>``). A running lazer
gets it through its IPC channel; a closed one starts and imports it. lazer deletes each .osz once it is imported,
so the downloads are handed over from osu! coach's own data folder (``lazer-maps``) and nothing is left behind.

Collections can't go in that way: lazer only takes them from "import from a previous osu! version" (Settings →
General → Run setup wizard → Import), which accepts any folder that looks like an osu!stable install — one with an
``osu!.*.cfg`` file or a ``Songs`` folder — and imports the beatmap folders inside ``Songs`` first and
``collection.db`` after that. osu! coach makes that folder in its data folder (``lazer-import/<playlist>``):

    <folder>/osu!.user.cfg     empty, marks the folder as a stable install
    <folder>/collection.db     the playlist
    <folder>/Songs/<set id>/   maps you don't have yet, unpacked from their .osz, when lazer's program
                               wasn't found to hand them to
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from collections.abc import Callable, Sequence
from contextlib import closing
from pathlib import Path

from osu_coach.config import default_cache_dir
from osu_coach.infra import clock
from osu_coach.infra.beatmaps import sources
from osu_coach.infra.exports.collection_db import dumps, write_collection_db

STABLE_MARKER = "osu!.user.cfg"
PACK_DIR = "lazer-import"  # in the data folder: one folder per playlist, for lazer's import screen
MAPS_DIR = "lazer-maps"  # in the data folder: .osz files on their way into lazer
KEEP_PACKS_S = 24 * 3600  # older import folders are removed when a new one is made
COMMAND_LINE_CHARS = 30000  # Windows allows 32,767 characters on a command line


def safe_name(name: str) -> str:
    """A folder name without characters Windows forbids and without dots: lazer routes a
    dropped path by its extension, and only an extension-less folder reaches the import screen."""
    s = re.sub(r'[\\/:*?"<>|]+', " ", str(name)).replace(".", ",").strip()
    return re.sub(r"\s+", " ", s)[:80].strip() or "osu-coach playlist"


def default_pack_dir(name: str, data_dir: Path | str | None = None) -> Path:
    """``<data folder>/lazer-import/<playlist>``. The data folder is in AppData, which lazer's own folder picker
    hides, so the folder is opened in the file manager to be dragged onto lazer."""
    return Path(data_dir or default_cache_dir()) / PACK_DIR / safe_name(name)


def is_pack(folder: Path) -> bool:
    return folder.is_dir() and (folder / STABLE_MARKER).is_file()


def find_pack(name: str, data_dir: Path | str | None = None) -> Path | None:
    """The import folder made for ``name``, taken from the ``lazer-import`` folder's own listing (never a path built
    from the name, so it can't point anywhere else); None when there is none."""
    base = Path(data_dir or default_cache_dir()) / PACK_DIR
    wanted = safe_name(name)
    if not base.is_dir():
        return None
    return next((p for p in base.iterdir() if p.name == wanted and is_pack(p)), None)


def remove_pack(folder: Path) -> bool:
    """Delete an import folder osu! coach made (one with its marker file); anything else is left alone."""
    if not is_pack(folder):
        return False
    shutil.rmtree(folder, ignore_errors=True)
    return not folder.exists()


def remove_old_packs(base: Path, keep: Path | None = None, older_than_s: float = KEEP_PACKS_S) -> list[Path]:
    """Import folders in ``base`` made more than ``older_than_s`` ago (except ``keep``), removed."""
    gone = []
    if not base.is_dir():
        return gone
    now = clock.timestamp()
    for folder in base.iterdir():
        if keep is not None and folder == keep:
            continue
        try:
            old = now - (folder / STABLE_MARKER).stat().st_mtime > older_than_s
        except OSError:
            continue
        if old and remove_pack(folder):
            gone.append(folder)
    return gone


# ------------------------------------------------------------------ handing maps to lazer
def is_lazer(exe: Path) -> bool:
    """lazer's program (osu!stable's is also called osu!.exe, but has no osu.Game.dll next to it)."""
    return exe.is_file() and (exe.parent / "osu.Game.dll").is_file()


def _registered_osz_program() -> Path | None:
    """The program Windows opens .osz files with as lazer (lazer registers ``osu.File.osz`` for itself)."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\osu.File.osz\shell\open\command") as k:
            command = winreg.QueryValue(k, None)
    except (ImportError, OSError):
        return None
    m = re.match(r'\s*"([^"]+)"|\s*(\S+)', command or "")
    return Path(m.group(1) or m.group(2)) if m else None


def find_lazer(candidates: Sequence[Path] | None = None) -> Path | None:
    """osu!lazer's program: the one registered for .osz files, else the default install
    (``%LOCALAPPDATA%/osulazer/current/osu!.exe``). None with ``OSU_COACH_NO_AUTODETECT`` (tests) or when not
    found."""
    if candidates is None:
        if os.environ.get("OSU_COACH_NO_AUTODETECT", "").strip() not in ("", "0") or os.name != "nt":
            return None
        candidates = [p for p in (_registered_osz_program(),) if p]
        if os.environ.get("LOCALAPPDATA"):
            candidates.append(Path(os.environ["LOCALAPPDATA"]) / "osulazer" / "current" / "osu!.exe")
    return next((Path(c) for c in candidates if is_lazer(Path(c))), None)


def launch(exe: Path, files: Sequence[Path]) -> None:
    """Run lazer's program with the files: it hands them to a running lazer, or starts lazer with them. lazer
    keeps running on its own (not as a child that ends with osu! coach)."""
    args = [str(exe), *(str(f) for f in files)]
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    kw = {
        "cwd": str(Path(exe).parent),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    try:
        subprocess.Popen(args, creationflags=flags | (0x01000000 if os.name == "nt" else 0), **kw)  # breakaway
    except OSError:
        subprocess.Popen(args, creationflags=flags, **kw)  # a job that doesn't allow breaking away


def batches(files: Sequence[Path], limit: int = COMMAND_LINE_CHARS) -> list[list[Path]]:
    """The files in groups that fit on one command line."""
    out: list[list[Path]] = []
    size = 0
    for f in files:
        n = len(str(f)) + 3
        if not out or size + n > limit:
            out.append([])
            size = 0
        out[-1].append(f)
        size += n
    return out


def send_to_lazer(
    exe: Path,
    files: Sequence[Path],
    progress: Callable[[int, int, str], None] | None = None,
    run: Callable[[Path, Sequence[Path]], None] | None = None,
    wait_s: Callable[[int], float] = lambda n: 60.0 + 3.0 * n,
    poll_s: float = 0.5,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[list[Path], list[Path]]:
    """Hand the .osz files to lazer, a command line at a time, and wait for lazer to take them: it deletes each
    one it has imported. Returns (imported, still there after ``wait_s(files in the group)`` seconds: lazer may
    still be busy with them, or couldn't import them). ``progress`` raises to stop a cancelled job. ``run`` defaults
    to :func:`launch`."""
    run = run or launch
    files = [Path(f) for f in files]
    for group in batches(files):
        run(exe, group)
        deadline = clock() + wait_s(len(group))
        while any(f.exists() for f in group) and clock() < deadline:
            done = sum(not f.exists() for f in files)
            if progress:
                progress(done, len(files), f"lazer is importing the maps: {done} of {len(files)}")
            sleep(poll_s)
    return [f for f in files if not f.exists()], [f for f in files if f.exists()]


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
    "Drag the folder osu! coach opened onto the lazer window (lazer's own folder picker can't see the AppData "
    "folder it is in).",
    "Press **Import content from previous version**. The collection (and any maps in the folder) shows up in song "
    "select; then press **Delete the folder** here.",
]

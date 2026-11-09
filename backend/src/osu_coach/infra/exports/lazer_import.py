"""Get maps into osu!lazer and open them there.

Maps go in by themselves: lazer imports an .osz passed to its program (``osu!.exe <file.osz>``). A running lazer
gets it through its IPC channel; a closed one starts and imports it. lazer deletes each .osz once it is imported,
so the downloads are handed over from osu! coach's own data folder (``lazer-maps``) and nothing is left behind.

A map is opened the same way, with its link: ``osu!.exe osu://b/<beatmap id>`` shows the map's page in lazer with
that difficulty picked, and lazer's "Go to beatmap" button there jumps to it in song select. lazer has no way in
from outside straight to song select, nor one for collections (only "import from a previous osu! version").
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import zipfile
from collections.abc import Callable, Sequence
from contextlib import closing
from pathlib import Path

from osu_coach.infra import clock
from osu_coach.infra.beatmaps import sources

MAPS_DIR = "lazer-maps"  # in the data folder: .osz files on their way into lazer
KEEP_LEFTOVERS_S = 24 * 3600  # an .osz lazer hasn't taken (it waits while you play) is removed after a day
COMMAND_LINE_CHARS = 30000  # Windows allows 32,767 characters on a command line


def safe_name(name: str) -> str:
    """A folder name without characters Windows forbids and without dots."""
    s = re.sub(r'[\\/:*?"<>|]+', " ", str(name)).replace(".", ",").strip()
    return re.sub(r"\s+", " ", s)[:80].strip() or "osu-coach playlist"


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


def launch(exe: Path, args: Sequence[Path | str]) -> None:
    """Run lazer's program with .osz files or an ``osu://`` link: it hands them to a running lazer, or starts lazer
    with them. lazer keeps running on its own (not as a child that ends with osu! coach)."""
    args = [str(exe), *(str(a) for a in args)]
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


def download_and_send(
    exe: Path, sets: Sequence[int], folder: Path, progress: Callable[[int, int, str], None] | None = None
) -> dict:
    """Download the map sets as .osz into ``folder`` (the data folder's ``lazer-maps``) and hand them to lazer.
    Returns {"maps": downloaded set ids, "failed": not downloaded, "imported": taken by lazer, "not_imported": not
    taken when osu! coach stopped waiting}, each in the order of ``sets``. ``progress`` raises to stop a cancelled
    job."""
    sets = list(dict.fromkeys(int(s) for s in sets))
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.osz"):  # left from an earlier run
        try:
            if clock.timestamp() - old.stat().st_mtime > KEEP_LEFTOVERS_S:
                old.unlink()
        except OSError:
            pass
    ok, failed = [], []
    try:
        with closing(sources.download_many(sets, folder, progress)) as done:
            for sid, path in done:
                if path and zipfile.is_zipfile(path):
                    ok.append((sid, Path(path)))
                else:
                    failed.append(sid)
                    if path:
                        Path(path).unlink(missing_ok=True)
        if progress:  # a cancel during the last downloads stops here, before lazer gets anything
            progress(len(sets), len(sets), "Handing the maps to lazer…")
    except BaseException:
        for _, path in ok:
            path.unlink(missing_ok=True)
        raise
    ok.sort(key=lambda pair: sets.index(pair[0]))
    files = [path for _, path in ok]
    imported, left = send_to_lazer(exe, files, progress=progress) if files else ([], [])
    by_file = {path: sid for sid, path in ok}
    return {
        "maps": [sid for sid, _ in ok],
        "failed": sorted(failed, key=sets.index),
        "imported": [by_file[f] for f in imported],
        "not_imported": [by_file[f] for f in left],
    }


def map_link(beatmap_id: int) -> str:
    """lazer's link to a difficulty (as on the osu! website: ``/b/<id>``)."""
    return f"osu://b/{int(beatmap_id)}"


def open_map(exe: Path, beatmap_id: int, run: Callable[[Path, Sequence[Path | str]], None] | None = None) -> str:
    """Show the map's page in lazer with this difficulty picked (lazer starts if it is closed). Returns the link."""
    link = map_link(beatmap_id)
    (run or launch)(exe, [link])
    return link

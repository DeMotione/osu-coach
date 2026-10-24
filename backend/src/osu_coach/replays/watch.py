"""Notice the replays osu! saves while osu! coach runs: stable's ``Data/r`` and ``Replays`` folders, lazer's store.

Polling rather than OS notifications (no extra dependency, the same on every system). Adding a file to a folder
changes the folder's modification time, so a poll is one ``stat`` per watched folder: for lazer's store
(``files/<a>/<ab>/<sha256>``) its few thousand sub-folders, not its many thousands of files. A folder that changed
is listed; a file written or copied there after the watcher started is a candidate, reported once its size has
stayed the same from one poll to the next (osu! has finished writing it) and it reads as a replay.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from osu_coach.replays import locate
from osu_coach.replays.detect import Install

SLACK_S = 2.0  # a file this much older than the watcher's start still counts (clocks, coarse file times)


class _Folder:
    __slots__ = ("depth", "kind", "mtime")

    def __init__(self, kind: str, depth: int, mtime: int | None):
        self.kind, self.depth, self.mtime = kind, depth, mtime  # depth: levels of sub-folders above the files


def _mtime(path: Path) -> int | None:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def _entries(path: Path) -> list[os.DirEntry]:
    try:
        with os.scandir(path) as it:
            return list(it)
    except OSError:
        return []


def is_replay(path: Path, kind: str) -> bool:
    """A finished replay file: an .osr in stable's folders, a replay among lazer's extension-less store files."""
    if kind == "lazer":
        info = locate.classify(path)
        return bool(info and info.get("k") == "osr")
    return path.suffix.lower() == ".osr" and locate.replay_header(path) is not None


class ReplayWatcher:
    """Call :meth:`poll` every few seconds; it returns the new replay files, each once, as ``(path, kind)``."""

    def __init__(self, installs: Iterable[Install], clock: Callable[[], float] = time.time):
        self.started = clock()
        self._folders: dict[Path, _Folder] = {}
        self._pending: dict[Path, tuple[str, int]] = {}  # candidate -> (kind, size at the last poll)
        self._seen: set[Path] = set()
        for inst in installs:
            if inst.kind == "stable":
                for folder in inst.replay_dirs:  # Data/r (local scores), Replays (exported)
                    self._watch(Path(folder), "stable", 0)
            elif inst.kind == "lazer" and inst.files_dir is not None:
                self._watch(Path(inst.files_dir), "lazer", 2)

    @property
    def folders(self) -> int:
        return len(self._folders)

    def _watch(self, folder: Path, kind: str, depth: int, known: bool = True) -> None:
        """Watch ``folder``. ``known``: its contents now are old (at the start); a folder that turns up later is
        listed at the next poll, so the file it was made for is not missed."""
        if folder in self._folders:
            return
        self._folders[folder] = _Folder(kind, depth, _mtime(folder) if known else None)
        if depth and known:
            for entry in _entries(folder):
                if entry.is_dir():
                    self._watch(Path(entry.path), kind, depth - 1)

    def poll(self) -> list[tuple[Path, str]]:
        for folder, state in list(self._folders.items()):
            now = _mtime(folder)
            if now is None or now == state.mtime:
                continue
            state.mtime = now
            for entry in _entries(folder):
                path = Path(entry.path)
                if state.depth:
                    if entry.is_dir():
                        self._watch(path, state.kind, state.depth - 1, known=False)
                elif path not in self._seen and path not in self._pending and entry.is_file():
                    try:
                        st = entry.stat()
                    except OSError:
                        continue
                    # new here: written, or put here (a copy keeps its modification time; its creation time on
                    # Windows, its change time elsewhere is when it arrived)
                    if max(st.st_mtime, st.st_ctime) >= self.started - SLACK_S:
                        self._pending[path] = (state.kind, -1)
        found = []
        for path, (kind, size) in list(self._pending.items()):
            try:
                st = path.stat()
            except OSError:  # gone again (a temporary file)
                del self._pending[path]
                continue
            if st.st_size != size or not st.st_size:
                self._pending[path] = (kind, st.st_size)  # still being written: look again next time
                continue
            del self._pending[path]
            self._seen.add(path)
            if is_replay(path, kind):
                found.append((path, kind))
        return found

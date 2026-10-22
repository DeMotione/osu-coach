"""Read the replays and beatmaps inside a stable folder or a lazer store: list files, read headers and md5s
(cached between runs), recognise lazer's content-addressed files by their headers.

Where the folders are is found in :mod:`osu_coach.replays.detect`.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import heapq
import os
from collections import Counter
from pathlib import Path

from osu_coach.replays.osr import lazer_info, lazer_mod_acronyms, parse_header, peek_header

HEAD_BYTES = 1 << 16


# ------------------------------------------------------------------ scanning
# Bump when cached replay headers gain fields: headers cached by an older version are read again.
SCAN_VERSION = 2
# A replay file is written when (or after) the play happens. The slack covers replay dates in the
# wrong time zone, coarse file times and clock drift.
DATE_SLACK_S = 86400.0


def upgrade_index(index: dict) -> None:
    """Forget replay headers cached by an older version (they lack the lazer mods)."""
    if index.get("v") == SCAN_VERSION:
        return
    lz = index.get("lazer")
    if isinstance(lz, dict):
        for k in [k for k, v in lz.items() if isinstance(v, dict) and v.get("k") == "osr"]:
            del lz[k]
    index.pop("osr", None)
    index["v"] = SCAN_VERSION


def read_head(path: Path, n: int = HEAD_BYTES) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(n)


def replay_header(path: Path, head: bytes | None = None) -> dict | None:
    """Header fields of an .osr file (plus ``lazer_mods`` for lazer replays), or None."""
    try:
        head = read_head(path) if head is None else head
        whole = head if len(head) < HEAD_BYTES else None
        h = parse_header(head)
        if h is None and whole is None and peek_header(head) is not None:  # very long life-bar string
            whole = Path(path).read_bytes()
            h = parse_header(whole)
        if h and h["version"] >= 30000001:
            if whole is None:
                whole = Path(path).read_bytes()
            h["lazer_mods"] = lazer_mod_acronyms(lazer_info(whole))
    except OSError:
        return None
    if h:
        h["path"] = str(path)
    return h


def is_osu_text(head: bytes) -> bool:
    return head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"osu file format")


def file_md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def walk_files(folder: Path, suffixes: tuple[str, ...]):
    """os.walk based (faster than rglob, survives permission errors)."""
    for dirpath, _dirs, files in os.walk(folder, onerror=lambda e: None):
        for f in files:
            if f.lower().endswith(suffixes):
                yield Path(dirpath) / f


def list_files(folder, keep=None) -> list[tuple[str, float]]:
    """(path, modification time) of every file under ``folder`` whose name passes ``keep``.
    One scandir pass: on Windows the times come with the directory listing."""
    out: list[tuple[str, float]] = []
    stack = [str(folder)]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif keep is None or keep(e.name):
                            out.append((e.path, e.stat().st_mtime))
                    except OSError:
                        continue
        except OSError:
            continue
    return out


def play_time(h: dict) -> float:
    """When a replay was played, as a Unix time (replay dates are stored in UTC)."""
    try:
        return _dt.datetime.fromisoformat(h["timestamp"]).replace(tzinfo=_dt.UTC).timestamp()
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return 0.0


class NewestReplays:
    """Tells a newest-file-first scan when it may stop reading replays.

    A replay file is written when (or after) the play happens. So once the ``latest``-th newest
    play found for the player of interest is newer than the newest file still unread, none of
    the remaining files can be among that player's ``latest`` newest plays.  The player of
    interest is ``player`` ("*" = everybody together), or else whoever has the most replays so
    far, which on your own computer is you.  ``accept`` decides which replays count."""

    def __init__(self, latest: int, player: str | None = None, accept=None):
        self.latest = int(latest)
        self.player = player or None
        self.accept = accept or (lambda h: True)
        self.newest: dict[str, list[float]] = {}  # player -> min-heap of the newest play times
        self.counts: Counter = Counter()
        self.seen: set = set()

    def add(self, h: dict) -> None:
        key = (h.get("beatmap_md5"), h.get("timestamp"), h.get("score"), h.get("player"))
        if key in self.seen or not self.accept(h):
            return
        self.seen.add(key)
        self.counts[h.get("player", "")] += 1
        t = play_time(h)
        for who in (h.get("player", ""), "*"):
            heap = self.newest.setdefault(who, [])
            if len(heap) < self.latest:
                heapq.heappush(heap, t)
            elif t > heap[0]:
                heapq.heapreplace(heap, t)

    def target(self) -> str | None:
        if self.player:
            return self.player
        return self.counts.most_common(1)[0][0] if self.counts else None

    def done(self, next_mtime: float) -> bool:
        heap = self.newest.get(self.target() or "")
        return bool(heap) and len(heap) >= self.latest and heap[0] > next_mtime + DATE_SLACK_S


def _cached_md5(p: Path, cache: dict) -> str | None:
    try:
        st = p.stat()
    except OSError:
        return None
    key = str(p)
    hit = cache.get(key)
    if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
        return hit[2]
    try:
        md5 = file_md5(p)
    except OSError:
        return None
    cache[key] = [st.st_size, st.st_mtime_ns, md5]
    return md5


def _cached_header(p: Path, cache: dict) -> dict | None:
    try:
        st = p.stat()
    except OSError:
        return None
    key = str(p)
    hit = cache.get(key)
    if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
        h = hit[2]
    else:
        h = replay_header(p)
        if h:
            h.pop("path", None)
        cache[key] = [st.st_size, st.st_mtime_ns, h]
    return dict(h, path=key) if h else None


def scan_folder(
    folder: Path, index: dict, latest: int | None = None, player: str | None = None, accept=None
) -> tuple[list[dict], dict[str, str]]:
    """Replays (.osr) and beatmaps (.osu, md5-indexed) under a folder.  ``latest``: read the
    replays newest file first and stop once the newest ``latest`` plays are certain (see
    NewestReplays) instead of reading every replay."""
    md5_cache = index.setdefault("files", {})
    header_cache = index.setdefault("osr", {})
    files = list_files(Path(folder), lambda n: n.lower().endswith((".osr", ".osu")))
    osr = sorted((f for f in files if f[0].lower().endswith(".osr")), key=lambda f: f[1], reverse=True)
    picker = NewestReplays(latest, player, accept) if latest else None
    replays, maps = [], {}
    for path, mtime in osr:
        if picker and picker.done(mtime):
            break
        h = _cached_header(Path(path), header_cache)
        if h:
            replays.append(h)
            if picker:
                picker.add(h)
    for path, _ in files:
        if path.lower().endswith(".osu"):
            md5 = _cached_md5(Path(path), md5_cache)
            if md5:
                maps.setdefault(md5, path)
    return replays, maps


def _looks_like_osr(probe: bytes) -> bool:
    # game mode 0-3, then the version, then the beatmap MD5 string (0x0b = present)
    return probe[:1] in (b"\x00", b"\x01", b"\x02", b"\x03") and probe[5:6] in (b"\x0b", b"\x00")


def classify(path: Path) -> dict | None:
    """What a file in lazer's store is: {"k": "osu", "md5": ...}, {"k": "osr", "h": header} or
    {"k": "x"} (anything else). Audio, images etc. cost a 64-byte read. None if unreadable."""
    try:
        with open(path, "rb") as fh:
            probe = fh.read(64)
            if is_osu_text(probe):
                md5 = hashlib.md5(probe)
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    md5.update(chunk)
                return {"k": "osu", "md5": md5.hexdigest()}
            if not _looks_like_osr(probe):
                return {"k": "x"}
            head = probe + fh.read(HEAD_BYTES - len(probe))
    except OSError:
        return None
    h = replay_header(path, head)
    if h:
        h.pop("path", None)
    return {"k": "osr", "h": h} if h else {"k": "x"}


class LazerStore:
    """Replays and beatmaps in lazer's content-addressed file store (``files/a/ab/<sha256>``).
    Every file is classified once and cached for good: a hash name never changes content."""

    def __init__(self, files_dir, index: dict):
        self.files_dir = Path(files_dir)
        self.cache = index.setdefault("lazer", {})
        self.unread: list[tuple[str, float]] = []  # files a limited scan skipped, newest first

    @property
    def exhausted(self) -> bool:
        return not self.unread

    def _info(self, path: str) -> dict | None:
        name = os.path.basename(path)
        info = self.cache.get(name)
        if info is None:
            info = classify(Path(path))
            if info is not None:
                self.cache[name] = info
        return info

    def scan(
        self, progress=None, latest: int | None = None, player: str | None = None, accept=None
    ) -> tuple[list[dict], dict[str, str]]:
        """Replays and beatmaps.  ``latest``: newest files first, stop once the newest ``latest``
        plays are certain (see NewestReplays); the rest is left in ``unread`` for find()."""
        files = list_files(self.files_dir, lambda n: len(n) == 64)
        picker = None
        if latest:
            files.sort(key=lambda f: f[1], reverse=True)
            picker = NewestReplays(latest, player, accept)
        self.unread = []
        replays, maps = [], {}
        for i, (path, mtime) in enumerate(files):
            if picker and picker.done(mtime):
                self.unread = files[i:]
                break
            if progress and i and i % 2000 == 0:
                progress(f"lazer files scanned: {i}")
            info = self._info(path)
            if info is None:
                continue
            if info["k"] == "osu":
                maps.setdefault(info["md5"], path)
            elif info["k"] == "osr":
                h = dict(info["h"], path=path)
                replays.append(h)
                if picker:
                    picker.add(h)
        return replays, maps

    def find(self, md5s, progress=None) -> dict[str, str]:
        """Read the files a limited scan skipped (newest first) until every beatmap in ``md5s``
        has turned up. Returns all beatmaps seen on the way."""
        remaining = set(md5s)
        maps: dict[str, str] = {}
        i = 0
        while i < len(self.unread) and remaining:
            path = self.unread[i][0]
            i += 1
            if progress and i % 500 == 0:
                progress(f"looking for beatmaps in lazer's files: {i}")
            info = self._info(path)
            if info and info["k"] == "osu":
                maps.setdefault(info["md5"], path)
                remaining.discard(info["md5"])
        self.unread = self.unread[i:]
        return maps


class SongsFolder:
    """osu!stable's Songs folder: beatmaps by MD5 (cached per file, keyed by size and time)."""

    def __init__(self, songs, index: dict):
        self.songs = Path(songs)
        self.cache = index.setdefault("files", {})
        self.unread: list[tuple[str, float]] | None = None  # .osu files not hashed yet (find)

    @property
    def exhausted(self) -> bool:
        return self.unread is not None and not self.unread

    def scan(self, progress=None) -> dict[str, str]:
        """Every beatmap in the folder."""
        maps = {}
        for i, p in enumerate(walk_files(self.songs, (".osu",))):
            if progress and i % 1000 == 0 and i:
                progress(f"beatmaps indexed: {i}")
            md5 = _cached_md5(p, self.cache)
            if md5:
                maps.setdefault(md5, str(p))
        self.unread = []
        return maps

    def find(self, md5s, progress=None) -> dict[str, str]:
        """Hash .osu files newest first until every beatmap in ``md5s`` has turned up."""
        if self.unread is None:
            self.unread = sorted(
                list_files(self.songs, lambda n: n.lower().endswith(".osu")), key=lambda f: f[1], reverse=True
            )
        remaining = set(md5s)
        maps: dict[str, str] = {}
        i = 0
        while i < len(self.unread) and remaining:
            path = self.unread[i][0]
            i += 1
            if progress and i % 500 == 0:
                progress(f"looking for beatmaps in Songs: {i}")
            md5 = _cached_md5(Path(path), self.cache)
            if md5:
                maps.setdefault(md5, path)
                remaining.discard(md5)
        self.unread = self.unread[i:]
        return maps


def scan_lazer_store(files_dir: Path, index: dict, progress=None) -> tuple[list[dict], dict[str, str]]:
    """Every replay and beatmap in lazer's file store (see LazerStore)."""
    return LazerStore(files_dir, index).scan(progress)


def index_songs(songs: Path, index: dict, progress=None) -> dict[str, str]:
    return SongsFolder(songs, index).scan(progress)

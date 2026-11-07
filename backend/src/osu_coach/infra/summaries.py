"""Per-play summaries, kept in SQLite (``summaries.sqlite`` in the osu-coach data folder).

A play is summarised once, when it is analysed (:func:`~osu_coach.domain.player.summarize`); the profile, the
progress months and the pages add the summaries up, so the session never holds every play's notes. Summaries of
plays analysed before this store existed are made once from their analysis cache files (:func:`summaries_of`).
A summary is saved with the analysis version and a fingerprint of the domain code that makes it
(:mod:`~osu_coach.infra.code_fingerprint`): when either changes, it is made again, with no version to bump by hand.

The store only saves work: when it can't be used (locked by another osu-coach, disk full, read-only), the
summaries are made in memory and not kept; a file that isn't a readable database is moved aside to
``summaries.sqlite.corrupt`` (not deleted, it may hold the only copy of some plays) and a new one is started.
"""

from __future__ import annotations

import logging
import os
import pickle
import sqlite3
import zlib
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import TypeVar

from osu_coach.domain.analysis.models import ANALYSIS_VERSION, Play
from osu_coach.domain.player import PlaySummary
from osu_coach.domain.player import summarize as summarize_play
from osu_coach.infra.code_fingerprint import fingerprint

DB_FILE = "summaries.sqlite"
# text with a prefix, so SQLite never takes it for a number
VERSION = f"a{ANALYSIS_VERSION}-{fingerprint('osu_coach.domain')}"
CHUNK = 50  # plays summarised and stored at a time when summaries are made from the analysis cache


log = logging.getLogger(__name__)
T = TypeVar("T")


def _connect(cache_dir: Path | str) -> sqlite3.Connection:
    path = Path(cache_dir) / DB_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS summaries (key TEXT PRIMARY KEY, version INTEGER NOT NULL, data BLOB)")
    except BaseException:
        conn.close()
        raise
    return conn


def _set_aside(cache_dir: Path | str) -> bool:
    """Move an unreadable store (and its journal) out of the way, to a name no earlier one has; False if it can't
    be moved."""
    path = Path(cache_dir) / DB_FILE
    n = 1
    while (aside := path.with_name(f"{DB_FILE}.corrupt" + (f"-{n}" if n > 1 else ""))).exists():
        n += 1
    try:
        for suffix in ("-journal", "-wal", "-shm", ""):
            part = path.with_name(path.name + suffix)
            if part.exists():
                os.replace(part, aside.with_name(aside.name + suffix))
    except OSError:
        log.warning("could not move the unreadable %s aside", path, exc_info=True)
        return False
    log.warning("%s was not a readable database; moved it to %s and started a new one", path, aside.name)
    return True


def _use(cache_dir: Path | str, work: Callable[[sqlite3.Connection], T], fallback: T) -> T:
    """``work(connection)``, or ``fallback`` when the store can't be used (see the module docstring)."""
    for attempt in range(2):
        try:
            conn = _connect(cache_dir)
            try:
                return work(conn)
            finally:
                conn.close()
        except sqlite3.OperationalError:  # locked, read-only, disk full: try again next time
            log.warning("the play summaries store can't be used right now", exc_info=True)
            return fallback
        except sqlite3.DatabaseError:  # not a database / malformed
            if attempt or not _set_aside(cache_dir):
                log.warning("the play summaries store is unreadable", exc_info=True)
                return fallback
    return fallback


def _pack(summary: PlaySummary) -> bytes:
    return zlib.compress(pickle.dumps(summary, protocol=pickle.HIGHEST_PROTOCOL), 6)


def _unpack(data: bytes) -> PlaySummary | None:
    try:
        summary = pickle.loads(zlib.decompress(data))
    except Exception:  # noqa: BLE001 - an unreadable row is made again
        return None
    return summary if isinstance(summary, PlaySummary) else None


def load(cache_dir: Path | str, keys: Iterable[str]) -> dict[str, PlaySummary]:
    """The stored summaries of these plays that are of the current version."""
    keys = list(dict.fromkeys(keys))
    if not keys:
        return {}

    def read(conn: sqlite3.Connection) -> dict[str, PlaySummary]:
        out: dict[str, PlaySummary] = {}
        for start in range(0, len(keys), 500):
            chunk = keys[start : start + 500]
            rows = conn.execute(
                f"SELECT key, data FROM summaries WHERE version = ? AND key IN ({', '.join('?' * len(chunk))})",
                [VERSION, *chunk],
            )
            for key, data in rows:
                summary = _unpack(data)
                if summary is not None:
                    out[key] = summary
        return out

    return _use(cache_dir, read, {})


def save(cache_dir: Path | str, summaries: Iterable[PlaySummary]) -> None:
    rows = [(s.key, VERSION, _pack(s)) for s in summaries]
    if not rows:
        return

    def write(conn: sqlite3.Connection) -> None:
        with conn:
            conn.executemany("INSERT OR REPLACE INTO summaries (key, version, data) VALUES (?, ?, ?)", rows)

    _use(cache_dir, write, None)


def summarize(cache_dir: Path | str, plays: Sequence[Play]) -> list[PlaySummary]:
    """The summaries of these analysed plays (the stored ones, the others made and stored), in their order."""
    have = load(cache_dir, [p.key for p in plays])
    new = [summarize_play(p) for p in plays if p.key not in have]
    save(cache_dir, new)
    made = {s.key: s for s in new}
    return [have.get(p.key) or made[p.key] for p in plays]


def summaries_of(
    cache_dir: Path | str, keys: Sequence[str], load_cached: Callable[[list[str]], list[Play]]
) -> list[PlaySummary]:
    """The summaries of these plays: stored ones, the others made from their analysis cache files
    (``load_cached(keys)``) and stored, ``CHUNK`` at a time so an interrupted run keeps what it made. Plays found in
    neither are left out."""
    have = load(cache_dir, keys)
    missing = [k for k in keys if k not in have]
    for start in range(0, len(missing), CHUNK):
        new = [summarize_play(p) for p in load_cached(missing[start : start + CHUNK])]
        save(cache_dir, new)
        have.update({s.key: s for s in new})
    return [have[k] for k in keys if k in have]

"""Per-play summaries, kept in SQLite (``summaries.sqlite`` in the osu-coach data folder).

A play is summarised once, when it is analysed (:func:`~osu_coach.domain.player.summarize`); the profile, the
progress months and the pages add the summaries up, so the session never holds every play's notes. Summaries of
plays analysed before this store existed are made once from their analysis cache files (:func:`summaries_of`).
A summary is saved with ``SUMMARY_VERSION`` and the analysis version: when either changes, it is made again.
"""

from __future__ import annotations

import pickle
import sqlite3
import zlib
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from osu_coach.domain.analysis.models import ANALYSIS_VERSION, Play
from osu_coach.domain.player import PlaySummary
from osu_coach.domain.player import summarize as summarize_play

DB_FILE = "summaries.sqlite"
SUMMARY_VERSION = 2  # bump when PlaySummary (or what goes into it) changes
VERSION = ANALYSIS_VERSION * 1000 + SUMMARY_VERSION
CHUNK = 50  # plays summarised and stored at a time when summaries are made from the analysis cache


def _connect(cache_dir: Path | str) -> sqlite3.Connection:
    path = Path(cache_dir) / DB_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS summaries (key TEXT PRIMARY KEY, version INTEGER NOT NULL, data BLOB)")
    return conn


def _pack(summary: PlaySummary) -> bytes:
    return zlib.compress(pickle.dumps(summary, protocol=pickle.HIGHEST_PROTOCOL), 6)


def _unpack(data: bytes) -> PlaySummary | None:
    try:
        return pickle.loads(zlib.decompress(data))
    except Exception:  # noqa: BLE001 - an unreadable row is made again
        return None


def load(cache_dir: Path | str, keys: Iterable[str]) -> dict[str, PlaySummary]:
    """The stored summaries of these plays that are of the current version."""
    keys = list(dict.fromkeys(keys))
    out: dict[str, PlaySummary] = {}
    if not keys:
        return out
    conn = _connect(cache_dir)
    try:
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
    finally:
        conn.close()
    return out


def save(cache_dir: Path | str, summaries: Iterable[PlaySummary]) -> None:
    rows = [(s.key, VERSION, _pack(s)) for s in summaries]
    if not rows:
        return
    conn = _connect(cache_dir)
    try:
        with conn:
            conn.executemany("INSERT OR REPLACE INTO summaries (key, version, data) VALUES (?, ?, ?)", rows)
    finally:
        conn.close()


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

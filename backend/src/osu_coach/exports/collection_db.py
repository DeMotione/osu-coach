"""osu!stable ``collection.db`` reader / writer / merger.

Format (all little-endian): Int32 version, Int32 collection count, then per
collection an osu! String name, Int32 beatmap count and that many osu! String
MD5 hashes. osu! Strings are 0x00 (null) or 0x0B + ULEB128 byte length + UTF-8.

The same file is what osu!lazer's "import from previous version" and tools like
Collection Manager read, so one exported file works for both clients.
"""
from __future__ import annotations

import datetime as _dt
import os
import shutil
import struct
from pathlib import Path

from osu_coach.exports.domain import merge_collections

DEFAULT_VERSION = 20150203   # same version osu-collect / osu-db write


def _uleb(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _write_string(buf: bytearray, s: str | None):
    if s is None:
        buf.append(0)
        return
    raw = s.encode("utf-8")
    buf.append(0x0B)
    buf += _uleb(len(raw))
    buf += raw


class _Reader:
    def __init__(self, data: bytes):
        self.d = data
        self.i = 0

    def take(self, n: int) -> bytes:
        if self.i + n > len(self.d):
            raise ValueError("collection.db is truncated")
        b = self.d[self.i:self.i + n]
        self.i += n
        return b

    def int(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def string(self) -> str:
        flag = self.take(1)[0]
        if flag == 0:
            return ""
        if flag != 0x0B:
            raise ValueError(f"bad string marker 0x{flag:02x} at {self.i - 1}")
        n = shift = 0
        while True:
            b = self.take(1)[0]
            n |= (b & 0x7F) << shift
            if not b & 0x80:
                break
            shift += 7
        return self.take(n).decode("utf-8", errors="replace")


def _normalise(collections) -> list[tuple[str, list[str]]]:
    items = collections.items() if isinstance(collections, dict) else collections
    out = []
    for name, hashes in items:
        seen: set[str] = set()
        clean = []
        for h in hashes:
            h = (h or "").strip().lower()
            if h and h not in seen:
                seen.add(h)
                clean.append(h)
        out.append((str(name), clean))
    return out


def dumps(collections, version: int = DEFAULT_VERSION) -> bytes:
    """``collections``: {name: [md5, ...]} or [(name, [md5, ...]), ...]."""
    cols = _normalise(collections)
    buf = bytearray(struct.pack("<ii", int(version), len(cols)))
    for name, hashes in cols:
        _write_string(buf, name)
        buf += struct.pack("<i", len(hashes))
        for h in hashes:
            _write_string(buf, h)
    return bytes(buf)


def loads(data: bytes) -> tuple[int, list[tuple[str, list[str]]]]:
    r = _Reader(data)
    version = r.int()
    count = r.int()
    if count < 0 or count > 1_000_000:
        raise ValueError("not a collection.db file")
    cols = []
    for _ in range(count):
        name = r.string()
        n = r.int()
        if n < 0 or n > 10_000_000:
            raise ValueError("not a collection.db file")
        cols.append((name, [r.string() for _ in range(n)]))
    return version, cols


def read_collection_db(path) -> tuple[int, list[tuple[str, list[str]]]]:
    return loads(Path(path).read_bytes())


def write_collection_db(path, collections, version: int = DEFAULT_VERSION) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(dumps(collections, version))
    os.replace(tmp, path)
    return path


def merge_into(path, new_collections, backup: bool = True) -> dict:
    """Add collections to an existing collection.db (osu! must be closed —
    osu! rewrites the file on exit). Same-name collections are replaced, all
    other collections are kept untouched; the original file is backed up."""
    path = Path(path)
    version, existing = DEFAULT_VERSION, []
    backup_path = None
    if path.exists():
        version, existing = read_collection_db(path)
        if backup:
            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = path.with_name(f"{path.name}.osu-coach-backup-{stamp}")
            shutil.copy2(path, backup_path)
    merged, replaced, added = merge_collections(existing, _normalise(new_collections))
    write_collection_db(path, merged, version)
    return {"path": str(path), "backup": str(backup_path) if backup_path else None, "replaced": replaced,
            "added": added, "collections": len(merged)}

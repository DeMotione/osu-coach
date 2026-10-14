"""Parser for osu! replay files (.osr), stable and lazer-exported.

Format reference: osu! wiki "osr (file format)" and lazer's LegacyScoreDecoder.
Frame clean-up follows lazer's decoder (which mirrors stable's ReplayWatcher):
seed frame removed, the two (256,-500) skip frames removed, no backwards time.
"""

from __future__ import annotations

import datetime as _dt
import io
import json
import lzma
import struct
from pathlib import Path

import numpy as np

from osu_coach.replays.domain import Replay, mods_to_string


class _Reader:
    def __init__(self, data: bytes):
        self.b = io.BytesIO(data)

    def byte(self) -> int:
        return struct.unpack("<B", self._read(1))[0]

    def short(self) -> int:
        return struct.unpack("<H", self._read(2))[0]

    def int(self) -> int:
        return struct.unpack("<i", self._read(4))[0]

    def long(self) -> int:
        return struct.unpack("<q", self._read(8))[0]

    def uleb(self) -> int:
        result = shift = 0
        while True:
            b = self.byte()
            result |= (b & 0x7F) << shift
            if not b & 0x80:
                return result
            shift += 7

    def string(self) -> str:
        flag = self.byte()
        if flag == 0x00:
            return ""
        if flag != 0x0B:
            raise ValueError(f"bad string flag {flag:#x}")
        n = self.uleb()
        return self._read(n).decode("utf-8", errors="replace")

    def remaining(self) -> int:
        pos = self.b.tell()
        end = self.b.seek(0, 2)
        self.b.seek(pos)
        return end - pos

    def _read(self, n: int) -> bytes:
        d = self.b.read(n)
        if len(d) != n:
            raise EOFError("unexpected end of replay file")
        return d


def _lzma_decode(data: bytes) -> str:
    if not data:
        return ""
    try:
        raw = lzma.decompress(data, format=lzma.FORMAT_ALONE)
    except lzma.LZMAError:
        # Some writers put a real size in the header and pad: decode leniently.
        dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        raw = dec.decompress(data)
    return raw.decode("ascii", errors="replace")


def _ticks_to_datetime(ticks: int) -> _dt.datetime:
    try:
        return _dt.datetime(1, 1, 1) + _dt.timedelta(microseconds=ticks // 10)
    except (OverflowError, ValueError):
        return _dt.datetime(1970, 1, 1)


def _parse_frames(text: str):
    ts, xs, ys, ks = [], [], [], []
    seed = None
    last = 0
    for chunk in text.split(","):
        parts = chunk.split("|")
        if len(parts) < 4:
            continue
        if parts[0] == "-12345":
            try:
                seed = int(parts[3])
            except ValueError:
                pass
            continue
        try:
            diff = int(parts[0])
        except ValueError:
            diff = int(round(float(parts[0])))
        last += diff
        ts.append(last)
        xs.append(float(parts[1]))
        ys.append(float(parts[2]))
        ks.append(int(float(parts[3])))

    # stable ReplayWatcher fix-ups (see lazer LegacyScoreDecoder.readLegacyReplay)
    if len(ts) >= 2 and ts[1] < ts[0]:
        ts[1] = ts[0]
        ts[0] = 0
    if len(ts) >= 3 and ts[0] > ts[2]:
        ts[0] = ts[1] = ts[2]
    for idx in (1, 0):
        if len(ts) > idx and xs[idx] == 256 and ys[idx] == -500:
            del ts[idx], xs[idx], ys[idx], ks[idx]

    out_t, out_x, out_y, out_k = [], [], [], []
    for t, x, y, k in zip(ts, xs, ys, ks):
        if out_t and t < out_t[-1]:
            continue  # never allow backwards time traversal
        out_t.append(t)
        out_x.append(x)
        out_y.append(y)
        out_k.append(k)
    return (
        np.asarray(out_t, dtype=np.int64),
        np.asarray(out_x, dtype=np.float64),
        np.asarray(out_y, dtype=np.float64),
        np.asarray(out_k, dtype=np.int64),
        seed,
    )


def parse_replay(data: bytes, source_path: str | None = None) -> Replay:
    r = _Reader(data)
    mode = r.byte()
    version = r.int()
    beatmap_md5 = r.string()
    player = r.string()
    replay_md5 = r.string()
    n300, n100, n50, ngeki, nkatu, nmiss = (r.short() for _ in range(6))
    score = r.int()
    max_combo = r.short()
    perfect = bool(r.byte())
    mods = r.int()
    life_bar = r.string()
    ts = _ticks_to_datetime(r.long())
    clen = r.int()
    compressed = r._read(clen) if clen > 0 else b""
    online_id = 0
    if r.remaining() >= 8 and version >= 20140721:
        online_id = r.long()
    elif r.remaining() >= 4 and version >= 20121008:
        online_id = r.int()
    lazer = None
    if version >= 30000001 and r.remaining() >= 4:
        n = r.int()
        if 0 < n <= r.remaining():
            try:
                lazer = json.loads(_lzma_decode(r._read(n)))
            except (ValueError, lzma.LZMAError):
                lazer = None
    t, x, y, k, seed = _parse_frames(_lzma_decode(compressed))
    return Replay(
        mode=mode,
        version=version,
        beatmap_md5=beatmap_md5,
        player=player,
        replay_md5=replay_md5,
        n300=n300,
        n100=n100,
        n50=n50,
        ngeki=ngeki,
        nkatu=nkatu,
        nmiss=nmiss,
        score=score,
        max_combo=max_combo,
        perfect=perfect,
        mods=mods,
        life_bar=life_bar,
        timestamp=ts,
        online_id=online_id,
        t=t,
        x=x,
        y=y,
        keys=k,
        rng_seed=seed,
        lazer=lazer,
        source_path=source_path,
    )


def parse_replay_file(path) -> Replay:
    p = Path(path)
    return parse_replay(p.read_bytes(), source_path=str(p))


def lazer_info(data: bytes) -> dict | None:
    """lazer's score info (mods with their settings, statistics, ...) from a whole .osr file,
    without decoding the replay frames.  None for stable replays or if it can't be read."""
    try:
        r = _Reader(data)
        r.byte()
        version = r.int()
        if version < 30000001:
            return None
        for _ in range(3):
            r.string()
        for _ in range(6):
            r.short()
        r.int(), r.short(), r.byte(), r.int()
        r.string()  # life bar graph
        r.long()  # timestamp
        clen = r.int()
        if clen > 0:
            r._read(clen)
        if r.remaining() >= 8:
            r.long()  # online score id
        if r.remaining() < 4:
            return None
        n = r.int()
        if not 0 < n <= r.remaining():
            return None
        info = json.loads(_lzma_decode(r._read(n)))
        return info if isinstance(info, dict) else None
    except (ValueError, EOFError, struct.error, IndexError, OverflowError, lzma.LZMAError):
        return None


def lazer_mod_acronyms(info: dict | None) -> list[str]:
    return [
        str(m.get("acronym", "")).upper()
        for m in (info or {}).get("mods", []) or []
        if isinstance(m, dict) and m.get("acronym")
    ]


def peek_header(data: bytes) -> dict | None:
    """Cheap check whether bytes look like an .osr; returns basic header fields or None."""
    try:
        if len(data) < 40 or data[0] > 3:
            return None
        r = _Reader(data)
        mode = r.byte()
        version = r.int()
        if not (20000000 <= version <= 40000000):
            return None
        if data[5] != 0x0B or data[6] != 32:
            return None
        md5 = r.string()
        if len(md5) != 32 or any(c not in "0123456789abcdef" for c in md5):
            return None
        player = r.string()
        return {"mode": mode, "version": version, "beatmap_md5": md5, "player": player}
    except (ValueError, EOFError, struct.error):
        return None


def parse_header(data: bytes) -> dict | None:
    """All header fields up to the timestamp, without decoding the frames (cheap).
    Returns None for anything that isn't an .osr (or is truncated)."""
    if peek_header(data) is None:
        return None
    try:
        r = _Reader(data)
        mode, version = r.byte(), r.int()
        md5, player, replay_md5 = r.string(), r.string(), r.string()
        n300, n100, n50, ngeki, nkatu, nmiss = (r.short() for _ in range(6))
        score, max_combo, perfect, mods = r.int(), r.short(), bool(r.byte()), r.int()
        r.string()  # life bar graph
        ts = _ticks_to_datetime(r.long())
    except (ValueError, EOFError, struct.error, IndexError, OverflowError, OSError):
        return None
    total = n300 + n100 + n50 + nmiss
    acc = (300 * n300 + 100 * n100 + 50 * n50) / (300 * total) if total else 0.0
    return {
        "mode": mode,
        "version": version,
        "beatmap_md5": md5,
        "player": player,
        "replay_md5": replay_md5,
        "n300": n300,
        "n100": n100,
        "n50": n50,
        "nmiss": nmiss,
        "score": score,
        "max_combo": max_combo,
        "perfect": perfect,
        "mods": mods,
        "mod_string": mods_to_string(mods),
        "timestamp": ts.isoformat(),
        "accuracy": acc,
        "is_lazer": version >= 30000000,
    }

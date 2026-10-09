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
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# Legacy mod bits (osu! API v1 / replay header)
MOD_BITS = {
    "NF": 1, "EZ": 2, "TD": 4, "HD": 8, "HR": 16, "SD": 32, "DT": 64, "RX": 128,
    "HT": 256, "NC": 512, "FL": 1024, "AT": 2048, "SO": 4096, "AP": 8192, "PF": 16384,
    "FI": 1048576, "RD": 2097152, "CN": 4194304, "TP": 8388608, "V2": 536870912, "MR": 1073741824,
}
_DISPLAY_ORDER = ["EZ", "NF", "HT", "TD", "HD", "HR", "SD", "PF", "DT", "NC", "FL", "RX", "AP", "SO", "AT", "CN", "V2", "MR"]

KEY_M1, KEY_M2, KEY_K1, KEY_K2, KEY_SMOKE = 1, 2, 4, 8, 16

LAZER_VERSION = 30000000


def has_mod(mods: int, name: str) -> bool:
    return bool(mods & MOD_BITS[name])


def mods_to_string(mods: int) -> str:
    names = []
    for n in _DISPLAY_ORDER:
        if mods & MOD_BITS[n]:
            if n == "DT" and mods & MOD_BITS["NC"]:
                continue
            if n == "SD" and mods & MOD_BITS["PF"]:
                continue
            names.append(n)
    return "".join(names) or "NM"


def rate_from_mods(mods: int) -> float:
    if mods & (MOD_BITS["DT"] | MOD_BITS["NC"]):
        return 1.5
    if mods & MOD_BITS["HT"]:
        return 0.75
    return 1.0


@dataclass
class Replay:
    mode: int
    version: int
    beatmap_md5: str
    player: str
    replay_md5: str
    n300: int
    n100: int
    n50: int
    ngeki: int
    nkatu: int
    nmiss: int
    score: int
    max_combo: int
    perfect: bool
    mods: int
    life_bar: str
    timestamp: _dt.datetime
    online_id: int
    t: np.ndarray = field(repr=False)      # absolute frame time, ms (map/audio time)
    x: np.ndarray = field(repr=False)      # osu!pixels, 0..512
    y: np.ndarray = field(repr=False)      # osu!pixels, 0..384
    keys: np.ndarray = field(repr=False)   # bitmask M1=1 M2=2 K1=4 K2=8 smoke=16
    rng_seed: int | None = None
    lazer: dict | None = None
    source_path: str | None = None

    @property
    def is_lazer(self) -> bool:
        return self.version >= LAZER_VERSION

    @property
    def mod_string(self) -> str:
        return mods_to_string(self.mods)

    @property
    def rate(self) -> float:
        """Playback rate; honours lazer's custom speed_change when present."""
        if self.lazer:
            for m in self.lazer.get("mods", []) or []:
                ac = str(m.get("acronym", "")).upper()
                if ac in ("DT", "NC", "HT", "DC"):
                    sc = (m.get("settings") or {}).get("speed_change")
                    if sc:
                        return float(sc)
                    return 0.75 if ac in ("HT", "DC") else 1.5
        return rate_from_mods(self.mods)

    @property
    def total_objects_judged(self) -> int:
        return self.n300 + self.n100 + self.n50 + self.nmiss

    @property
    def accuracy(self) -> float:
        tot = self.total_objects_judged
        if tot == 0:
            return 0.0
        return (300 * self.n300 + 100 * self.n100 + 50 * self.n50) / (300 * tot)


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
    return (np.asarray(out_t, dtype=np.int64), np.asarray(out_x, dtype=np.float64),
            np.asarray(out_y, dtype=np.float64), np.asarray(out_k, dtype=np.int64), seed)


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
    return Replay(mode=mode, version=version, beatmap_md5=beatmap_md5, player=player, replay_md5=replay_md5,
                  n300=n300, n100=n100, n50=n50, ngeki=ngeki, nkatu=nkatu, nmiss=nmiss, score=score,
                  max_combo=max_combo, perfect=perfect, mods=mods, life_bar=life_bar, timestamp=ts,
                  online_id=online_id, t=t, x=x, y=y, keys=k, rng_seed=seed, lazer=lazer,
                  source_path=source_path)


def parse_replay_file(path) -> Replay:
    p = Path(path)
    return parse_replay(p.read_bytes(), source_path=str(p))


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

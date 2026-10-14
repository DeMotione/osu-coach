"""Replay model and mod/key constants (parsing lives in osu_coach.replays.osr)."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

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

# lazer mods whose effect the simulation can't reproduce (speed or note positions change during the
# map, extra input rules): such replays are skipped with this reason
UNSUPPORTED_LAZER_MODS = {
    "WU": "Wind Up changes the speed during the map", "WD": "Wind Down changes the speed during the map",
    "AS": "Adaptive Speed changes the speed during the map", "RD": "Random moves the notes",
    "WG": "Wiggle moves the notes", "TR": "Transform moves the notes", "MG": "Magnetised moves the cursor",
    "RP": "Repel moves the cursor", "BR": "Barrel Roll rotates the playfield", "DP": "Depth moves the notes",
    "GR": "Grow changes the note size", "DF": "Deflate changes the note size", "SI": "Spin In changes the notes",
    "TP": "Target Practice replaces the map", "AL": "Alternate blocks some presses",
    "SG": "Single Tap blocks some presses", "ST": "Strict Tracking changes slider rules",
}


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

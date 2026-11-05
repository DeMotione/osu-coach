"""Canonical gameplay identity shared by replay evidence and map recommendations.

The recommendation rate grid is deliberately separate from replay identity: a
recorded custom speed is never rounded onto that grid.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from osu_coach.replays.domain import MOD_BITS, rate_from_mods


def canonical_mods(lazer_mods: list | None) -> str:
    """Stable representation including every lazer gameplay setting."""
    if not lazer_mods:
        return "[]"
    mods = []
    for mod in lazer_mods:
        acronym = str(mod.get("acronym", "")).upper()
        settings = dict(mod.get("settings") or {})
        if acronym in ("DT", "NC", "HT", "DC"):
            # speed_change is the absolute rate already stored on Configuration.
            settings.pop("speed_change", None)
        mods.append({"acronym": acronym, "settings": settings})
    # Stock legacy mods are already represented by their bitmask. Keep extra
    # lazer mods and every customized setting in the identity.
    mods = [mod for mod in mods if mod["settings"] or mod["acronym"] not in MOD_BITS]
    return json.dumps(
        sorted(mods, key=lambda mod: (mod["acronym"], json.dumps(mod["settings"], sort_keys=True))),
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class Configuration:
    md5: str
    mods: int = 0
    rate: float = 1.0
    client: str = "stable"
    lazer_mods: str = "[]"

    def __post_init__(self) -> None:
        if not math.isfinite(self.rate) or self.rate <= 0:
            raise ValueError("Playback rate must be finite and positive.")
        # Nightcore and Double Time have the same map mechanics at an equal
        # absolute rate; replay headers may set NC alone or NC together with DT.
        if self.mods & MOD_BITS["NC"]:
            object.__setattr__(self, "mods", (self.mods | MOD_BITS["DT"]) & ~MOD_BITS["NC"])

    @property
    def key(self) -> str:
        return json.dumps(
            [self.md5, self.mods, format(self.rate, ".17g"), self.client, self.lazer_mods], separators=(",", ":")
        )

    @property
    def hr(self) -> bool:
        return bool(self.mods & MOD_BITS["HR"])

    @property
    def hd(self) -> bool:
        return bool(self.mods & MOD_BITS["HD"])

    @property
    def dt(self) -> bool:
        return bool(self.mods & (MOD_BITS["DT"] | MOD_BITS["NC"]))


def from_meta(meta: dict) -> Configuration:
    mods = int(meta.get("mods") or 0)
    lazer_mods = meta.get("lazer_mods") or []
    for mod in lazer_mods:
        acronym = str(mod.get("acronym", "")).upper()
        if acronym in MOD_BITS:
            mods |= MOD_BITS[acronym]
        elif acronym == "DC":
            mods |= MOD_BITS["HT"]
    rate = meta.get("rate")
    if rate is None:
        rate = next(
            (
                (mod.get("settings") or {}).get("speed_change")
                for mod in lazer_mods
                if str(mod.get("acronym", "")).upper() in ("DT", "NC", "HT", "DC")
                and (mod.get("settings") or {}).get("speed_change") is not None
            ),
            rate_from_mods(mods),
        )
    return Configuration(
        md5=str(meta.get("beatmap_md5") or ""),
        mods=mods,
        rate=float(rate),
        client=str(meta.get("client") or "stable"),
        lazer_mods=canonical_mods(lazer_mods),
    )

"""The pool's pp table (``data/pool_pp.npz``): the pp of a full combo at the play goals' accuracies, for every pool
map in each of their mod combinations, played on stable and on lazer. Farm PP reads it instead of the maps' .osu
files: no download and no calculation a search.

Rebuild it after the pool and after a new rosu-pp with ``tools/build_pp_table.py`` (``tests/infra/test_pp_table.py``
fails while it is stale). The values are stored as uint16 (pp * ``scale``), each accuracy's as the difference from the
one before it (they pack well), in an LZMA-packed .npz; the whole table is read into memory (~10 MB).
"""

from __future__ import annotations

import json
import logging
import os
import zipfile
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path

import numpy as np

from osu_coach.domain.play_goals.pool import ACCURACIES, CONFIGS
from osu_coach.infra.beatmaps.performance import CALCULATOR_VERSION, pp_curve

log = logging.getLogger("osu_coach.infra.pp_table")

POOL_PP_PATH = Path(__file__).parent / "data" / "pool_pp.npz"
FORMAT = 1
CLIENTS = ("stable", "lazer")
SCALE = 4.0  # quarter pp: up to 16,383 pp
MISSING = 65535  # no value


@dataclass(frozen=True)
class PpTable:
    """The pp of the pool's maps by (map, mod combination, client, accuracy)."""

    md5: tuple[str, ...]
    pp: np.ndarray  # uint16 (maps, configs, clients, accuracies): pp * scale, MISSING for none
    configs: tuple[str, ...]
    clients: tuple[str, ...]
    accuracies: tuple[float, ...]
    scale: float = SCALE

    @cached_property
    def index(self) -> dict[str, int]:
        return {md5: i for i, md5 in enumerate(self.md5)}

    def curve(self, md5: str, config: str, client: str) -> list[dict] | None:
        """The map's pp curve in this combination and client (``[{"accuracy", "pp"}]``), None when the table has
        none (not a pool map, a combination it doesn't hold, or a map rosu couldn't calculate)."""
        i = self.index.get(md5)
        if i is None or config not in self.configs or client not in self.clients:
            return None
        values = self.pp[i, self.configs.index(config), self.clients.index(client)]
        if (values == MISSING).any():
            return None
        return [{"accuracy": a, "pp": float(v) / self.scale} for a, v in zip(self.accuracies, values, strict=True)]


def map_pp(raw: bytes) -> np.ndarray:
    """What the table holds of one map, from its .osu file: pp (configs, clients, accuracies), NaN where rosu has
    none (not an osu!standard map, no objects)."""
    out = np.full((len(CONFIGS), len(CLIENTS), len(ACCURACIES)), np.nan, dtype=np.float32)
    for c, mods in enumerate(CONFIGS.values()):
        for k, client in enumerate(CLIENTS):
            try:
                out[c, k] = pp_curve(raw, mods, client, ACCURACIES)
            except ValueError:
                pass
    return out


def save_pp_table(path: Path | str, md5: list[str], parts: list[np.ndarray | None], note: dict | None = None) -> Path:
    """Write the table of the maps ``md5`` from their parts (:func:`map_pp`; None: the map's file was not there)."""
    shape = (len(CONFIGS), len(CLIENTS), len(ACCURACIES))
    values = np.stack([np.full(shape, np.nan) if p is None else p for p in parts]) if parts else np.empty((0, *shape))
    with np.errstate(invalid="ignore"):
        stored = np.where(np.isfinite(values), np.minimum(np.rint(values * SCALE), MISSING - 1), MISSING)
    stored = stored.astype(np.uint16)
    stored[..., 1:] -= stored[..., :-1].copy()  # wrapping within uint16, undone on reading
    meta = {
        "format": FORMAT,
        "calculator_version": CALCULATOR_VERSION,
        "configs": list(CONFIGS),
        "clients": list(CLIENTS),
        "accuracies": list(ACCURACIES),
        "scale": SCALE,
        **(note or {}),
    }
    members = {"meta": np.array(json.dumps(meta)), "md5": np.array(md5, dtype="U32"), "pp": stored}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_LZMA) as archive:
        for name, array in members.items():
            with archive.open(name + ".npy", "w", force_zip64=True) as fh:
                np.lib.format.write_array(fh, array, allow_pickle=False)
    os.replace(temp, path)
    return path


def _usable(meta: dict) -> bool:
    return (
        meta.get("format") == FORMAT
        and meta.get("calculator_version") == CALCULATOR_VERSION
        and tuple(meta.get("configs") or ()) == tuple(CONFIGS)
        and tuple(meta.get("clients") or ()) == CLIENTS
        and tuple(meta.get("accuracies") or ()) == ACCURACIES
    )


def read_pp_table(path: Path | str) -> PpTable | None:
    """The table of a file; None when it was made for another calculator or other combinations."""
    with np.load(path, allow_pickle=False) as archive:
        meta = json.loads(str(archive["meta"]))
        if not _usable(meta):
            return None
        pp = np.cumsum(archive["pp"], axis=-1, dtype=np.uint16)
        md5 = tuple(str(m) for m in archive["md5"].tolist())
    return PpTable(md5, pp, tuple(meta["configs"]), tuple(meta["clients"]), tuple(meta["accuracies"]), meta["scale"])


@lru_cache(maxsize=2)
def _load(path: str, size: int, mtime: int) -> PpTable | None:
    try:
        table = read_pp_table(path)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        log.warning("The pp table could not be read (%s).", exc)
        return None
    if table is None:
        log.warning("The pp table was made for another calculator; rebuild it with tools/build_pp_table.py.")
    return table


def load_pp_table(path: Path | str | None = None) -> PpTable | None:
    """The bundled pp table (or the one at ``path``); None: there is none, or it was made for other versions."""
    p = Path(path or POOL_PP_PATH)
    try:
        stat = p.stat()
    except OSError:
        return None
    return _load(str(p), stat.st_size, stat.st_mtime_ns)

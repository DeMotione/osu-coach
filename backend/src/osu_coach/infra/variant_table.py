"""The variant table's file (``data/pool_variants.npz``): making a map's part from its .osu file, saving, loading.

What the table is and how it is read: ``osu_coach.domain.maps.variants``. Rebuild it after the pool with
``tools/build_variant_table.py``. The file is a .npz whose arrays are LZMA-packed, the big ones as differences along
the rate (they change little from one rate to the next); it is unpacked once into the data folder and read from
there as memory-mapped arrays, so a search touches only the values it asks for.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np

from osu_coach.domain.beatmaps.features import features_at_rate, object_features
from osu_coach.domain.beatmaps.models import PlayableBeatmap
from osu_coach.domain.maps.suggestions import pattern_stats
from osu_coach.domain.maps.variants import (
    BY_CONFIGURATION,
    BY_GEOMETRY,
    MISSING,
    PATTERN_COLUMNS,
    RATES,
    SCALES,
    VariantTable,
    segment_starts,
)
from osu_coach.domain.numeric.values import finite_or_none
from osu_coach.domain.player.algorithm import MODEL_VERSION
from osu_coach.domain.replays.models import MOD_BITS
from osu_coach.infra.beatmaps import difficulty
from osu_coach.infra.beatmaps.parser import parse_beatmap_bytes
from osu_coach.infra.beatmaps.performance import CALCULATOR_VERSION
from osu_coach.infra.map_stats import _evenness

log = logging.getLogger("osu_coach.infra.variant_table")

POOL_VARIANTS_PATH = Path(__file__).parent / "data" / "pool_variants.npz"
FORMAT = 1
_unpacking = threading.Lock()  # one thread unpacks the table, the others wait for it
_CHECKED = (0, RATES.index(150), len(RATES) - 1)  # rates at which a map's values are compared with stable's


def _number(value: float | None) -> float:
    value = finite_or_none(value)
    return np.nan if value is None or value < 0 else value


def _same(first: float | None, second: float | None) -> bool:
    first, second = _number(first), _number(second)
    return bool(first == second or (first != first and second != second) or abs(first - second) <= 1e-9)


def blank_variants() -> dict:
    """The part of a map nothing is known of (no file, or one without statistics): rosu's values of every
    configuration (NaN: none) and no pattern statistics."""
    out: dict = {name: np.full((2, 2, len(RATES)), np.nan, dtype=np.float32) for name in BY_CONFIGURATION}
    out.update({name: np.full((2, len(RATES)), np.nan, dtype=np.float32) for name in BY_GEOMETRY})
    out["segments"] = []  # (HR, rate index, the pattern statistics at that rate)
    out["differs"] = False
    return out


def map_variants(raw: bytes) -> dict:
    """What the table holds of one map, from its .osu file: the values ``variant_rows`` gives for every
    configuration of the grid, calculated the same way. ``differs``: stable's values or HD's slider factor and
    evenness are not the stored ones (they have been the same on every map so far; the table holds one of each)."""
    out = blank_variants()
    try:
        bm = parse_beatmap_bytes(raw)
    except Exception:  # noqa: BLE001 - a broken file has no statistics
        return out
    parsed = difficulty.parse_map(raw) if bm.mode == 0 and len(bm.objects) >= 30 else None
    if parsed is None or not any(o.kind != "spinner" for o in bm.objects):
        return out
    filled = blank_variants()
    for hr in (0, 1):
        geometry = MOD_BITS["HR"] if hr else 0
        template = object_features(PlayableBeatmap(bm, geometry, rate=1.0))
        exact = np.full((len(RATES), len(PATTERN_COLUMNS)), np.nan)
        for i, hundredths in enumerate(RATES):
            rate = hundredths / 100
            mods = geometry | (MOD_BITS["DT"] if hundredths != 100 else 0)
            pattern = pattern_stats(bm, raw, mods, rate, features_at_rate(template, rate))
            if pattern is None:
                return out
            unknown = [k for k, v in pattern.items() if k not in PATTERN_COLUMNS and not isinstance(v, str)]
            if set(unknown) - {"beatmap_id", "beatmapset_id"}:
                raise ValueError(f"pattern statistics the variant table has no column for: {unknown}")
            exact[i] = [v if (v := finite_or_none(pattern.get(c))) is not None else np.nan for c in PATTERN_COLUMNS]
            evenness = _evenness(raw, mods, rate, lazer=True, parsed_map=parsed)
            filled["evenness"][hr, i] = _number(evenness)
            for hd in (0, 1):
                with_hd = mods | (MOD_BITS["HD"] if hd else 0)
                a = difficulty.attributes(raw, with_hd, rate=rate, lazer=True, parsed_map=parsed)
                stars = finite_or_none(a.get("stars"))
                if stars is None or stars <= 0:
                    continue  # the configuration has no row
                for name in BY_CONFIGURATION:
                    filled[name][hr, hd, i] = _number(a.get(name))
                factor = a.get("slider_factor", 1.0)
                if hd == 0:
                    filled["slider_factor"][hr, i] = _number(factor)
                    kept = factor
                elif not _same(factor, kept):
                    filled["differs"] = True
                if i in _CHECKED:
                    stable = difficulty.attributes(raw, with_hd, rate=rate, lazer=False, parsed_map=parsed)
                    if not all(_same(stable.get(k), a.get(k)) for k in (*BY_CONFIGURATION, "slider_factor")):
                        filled["differs"] = True
                    if not _same(_evenness(raw, with_hd, rate, lazer=False, parsed_map=parsed), evenness):
                        filled["differs"] = True
        filled["segments"] += [(hr, i, exact[i].astype(np.float32)) for i in segment_starts(exact)]
    return filled


# ------------------------------------------------------------------ the file
def _packed(values: np.ndarray, scale: float) -> np.ndarray:
    """The values as uint16 (value * scale, MISSING for none), then as differences along the rate (and of HD from
    no HD), wrapping within uint16: small numbers pack well."""
    with np.errstate(invalid="ignore"):
        d = np.where(np.isfinite(values), np.minimum(np.rint(values.astype(np.float64) * scale), MISSING - 1), MISSING)
    d = d.astype(np.uint16)
    if d.ndim == 4:
        d[:, :, 1, :] -= d[:, :, 0, :]
    d[..., 1:] -= d[..., :-1].copy()
    return d


def _unpacked(d: np.ndarray) -> np.ndarray:
    values = np.cumsum(d, axis=-1, dtype=np.uint16)
    if values.ndim == 4:
        values[:, :, 1, :] += values[:, :, 0, :]
    return values


def save_table(
    path: Path | str,
    md5: list[str],
    parts: list[dict | None],
    note: dict | None = None,
    scales: dict[str, float] | None = None,
) -> Path:
    """Write the table of the maps ``md5`` from their parts (:func:`map_variants`; None: the map's file was not
    there), in that order. ``scales``: how finely each of rosu's values is stored (1 / the step)."""
    scales = scales or SCALES
    blank = blank_variants()
    arrays = {name: np.stack([(p or blank)[name] for p in parts]) for name in (*BY_CONFIGURATION, *BY_GEOMETRY)}
    keys, rows = [], []
    for i, part in enumerate(parts):
        for hr, rate, row in sorted((part or blank)["segments"], key=lambda s: (s[0], s[1])):
            keys.append((i * 2 + hr) * 128 + rate)
            rows.append(row)
    meta = {
        "format": FORMAT,
        "model_version": MODEL_VERSION,
        "calculator_version": CALCULATOR_VERSION,
        "columns": list(PATTERN_COLUMNS),
        "rates": list(RATES),
        "scales": scales,
        **(note or {}),
    }
    members = {
        "meta": np.array(json.dumps(meta)),
        "md5": np.array(md5, dtype="U32"),
        "found": np.array([p is not None for p in parts], dtype=bool),
        **{name: _packed(values, scales[name]) for name, values in arrays.items()},
        "segment_keys": np.array(keys, dtype=np.int64),
        "segment_rows": np.array(rows, dtype=np.float32).reshape(len(rows), len(PATTERN_COLUMNS)),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_LZMA) as archive:
        for name, values in members.items():
            with archive.open(name + ".npy", "w", force_zip64=True) as fh:
                np.lib.format.write_array(fh, values, allow_pickle=False)
    os.replace(temp, path)
    return path


def _usable(meta: dict) -> bool:
    return (
        meta.get("format") == FORMAT
        and meta.get("model_version") == MODEL_VERSION
        and meta.get("calculator_version") == CALCULATOR_VERSION
        and tuple(meta.get("rates") or ()) == RATES
        and set(PATTERN_COLUMNS) <= set(meta.get("columns") or ())
    )


def _table(meta: dict, arrays: dict) -> VariantTable:
    return VariantTable(
        md5=tuple(str(m) for m in arrays["md5"].tolist()),
        found=np.asarray(arrays["found"]),
        columns=tuple(meta["columns"]),
        scales={k: float(v) for k, v in meta["scales"].items()},
        **{name: arrays[name] for name in (*BY_CONFIGURATION, *BY_GEOMETRY, "segment_keys", "segment_rows")},
    )


def _unpack(path: Path, folder: Path) -> None:
    """The file's arrays as plain .npy files in ``folder`` (made whole, or not at all)."""
    temp = folder.with_name(f"{folder.name}.{os.getpid()}.tmp")
    shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir(parents=True)
    try:
        with np.load(path, allow_pickle=False) as archive:
            for name in archive.files:
                if name == "meta":
                    continue
                values = archive[name]
                np.save(
                    temp / f"{name}.npy", _unpacked(values) if name in (*BY_CONFIGURATION, *BY_GEOMETRY) else values
                )
            (temp / "meta.json").write_text(str(archive["meta"]), encoding="utf-8")
        try:
            os.replace(temp, folder)
        except OSError:
            if not (folder / "meta.json").exists():  # another process may have made it meanwhile
                raise
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    for other in folder.parent.iterdir():  # tables of earlier versions
        if other != folder and other.is_dir() and not other.name.endswith(".tmp"):
            shutil.rmtree(other, ignore_errors=True)


@lru_cache(maxsize=2)
def _load(path: str, size: int, mtime: int, cache_dir: str) -> VariantTable | None:
    folder = Path(cache_dir) / "recommendations" / "variant-table" / f"{size:x}-{mtime:x}"
    try:
        if not (folder / "meta.json").exists():
            _unpack(Path(path), folder)
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        if not _usable(meta):
            log.warning("The variant table was made for other versions; maps with mods are calculated instead.")
            return None
        names = ("md5", "found", *BY_CONFIGURATION, *BY_GEOMETRY, "segment_keys", "segment_rows")
        small = ("md5", "found", "segment_keys")
        arrays = {n: np.load(folder / f"{n}.npy", mmap_mode=None if n in small else "r") for n in names}
        return _table(meta, arrays)
    except (OSError, ValueError, KeyError) as exc:
        log.warning("The variant table could not be unpacked (%s); reading it into memory.", exc)
    try:
        return read_table(path)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        log.warning("The variant table could not be read (%s); maps with mods are calculated instead.", exc)
        return None


def read_table(path: Path | str, only: list[str] | None = None) -> VariantTable | None:
    """The table of a file, in memory: whole, or of the maps ``only`` (md5s the file lists). None: it was made for
    other versions of the statistics."""
    with np.load(path, allow_pickle=False) as archive:
        meta = json.loads(str(archive["meta"]))
        if not _usable(meta):
            return None
        packed = (*BY_CONFIGURATION, *BY_GEOMETRY)
        if only is None:
            arrays = {n: _unpacked(archive[n]) if n in packed else archive[n] for n in archive.files if n != "meta"}
            return _table(meta, arrays)
        listed = archive["md5"].tolist()
        maps = np.array([listed.index(md5) for md5 in only], dtype=np.int64)
        arrays = {n: _unpacked(archive[n][maps]) for n in packed}
        arrays.update(md5=np.array(only, dtype="U32"), found=archive["found"][maps])
        keys = archive["segment_keys"]
        new = np.full(len(listed), -1, dtype=np.int64)
        new[maps] = np.arange(len(maps))
        kept = np.flatnonzero(new[keys // 256] >= 0)
        kept = kept[np.argsort(new[keys[kept] // 256], kind="stable")]
        arrays["segment_keys"] = new[keys[kept] // 256] * 256 + keys[kept] % 256
        arrays["segment_rows"] = archive["segment_rows"][kept]
    return _table(meta, arrays)


def load_table(cache_dir: Path | str, path: Path | str | None = None) -> VariantTable | None:
    """The bundled variant table (or the one at ``path``), unpacked into ``cache_dir`` when it is not there yet.
    None: there is none, or it was made for other versions of the statistics."""
    p = Path(path or POOL_VARIANTS_PATH)
    try:
        stat = p.stat()
    except OSError:
        return None
    with _unpacking:
        return _load(str(p), stat.st_size, stat.st_mtime_ns, str(cache_dir))

"""How fast this computer analyses replays, next to the estimate's own numbers (``domain.analysis.estimate``):
measured by each analysis that analysed enough replays, kept in ``analysis_speed.json`` in the data folder."""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path

FILE = "analysis_speed.json"
ENOUGH = 20  # replays an analysis must have analysed to say something about the computer
WEIGHT = 0.5  # of the newest measurement against the ones before

log = logging.getLogger(__name__)


def speed(cache_dir: Path | str) -> float:
    """Times the estimate's computer this one takes (1 until measured)."""
    try:
        value = float(json.loads((Path(cache_dir) / FILE).read_text(encoding="utf-8"))["speed"])
    except (OSError, ValueError, KeyError, TypeError):
        return 1.0
    return value if math.isfinite(value) and 0.05 <= value <= 20 else 1.0


def record(cache_dir: Path | str, estimated: float, took: float, analysed: int) -> None:
    """An analysis estimated at ``estimated`` seconds (at speed 1) took ``took``: the speed moves towards it."""
    if analysed < ENOUGH or estimated <= 0 or not math.isfinite(took) or took <= 0:
        return
    measured = min(20.0, max(0.05, took / estimated))
    value = WEIGHT * measured + (1 - WEIGHT) * speed(cache_dir)
    path = Path(cache_dir) / FILE
    try:
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps({"speed": round(value, 4)}), encoding="utf-8")
        os.replace(temp, path)
    except OSError:  # the estimate stays as it was
        log.warning("could not save the analysis speed", exc_info=True)

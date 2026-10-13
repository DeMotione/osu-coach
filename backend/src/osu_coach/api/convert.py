"""Domain values (numpy / pandas scalars, NaN, naive UTC datetimes) to plain JSON-safe Python values."""
from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable

import pandas as pd


def num(v) -> float | None:
    """A finite float, None for None / NaN / ±inf / anything that isn't a number."""
    if v is None or isinstance(v, str):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def integer(v) -> int | None:
    f = num(v)
    return None if f is None else int(round(f))


def nums(values: Iterable) -> list[float | None]:
    return [num(v) for v in values]


def text(v) -> str | None:
    """A string, None for missing values (None, NaN, pd.NA)."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


def flag(v) -> bool | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return bool(v)


def iso(v) -> str | None:
    """A replay time as ISO 8601 in UTC (``...Z``); naive datetimes are UTC (as in replays)."""
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(v, pd.Timestamp):
        if pd.isna(v):
            return None
        v = v.to_pydatetime()
    if not isinstance(v, dt.datetime):
        return None
    v = v.replace(tzinfo=dt.UTC) if v.tzinfo is None else v.astimezone(dt.UTC)
    return v.isoformat(timespec="seconds").replace("+00:00", "Z")

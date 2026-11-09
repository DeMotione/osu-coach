"""Number checks shared by the domain."""

from __future__ import annotations

import math


def finite_or_none(value: object) -> float | None:
    """``value`` as a float, or None when it is missing, not a number (booleans and text count as not a number) or not
    finite."""
    kind = type(value)
    if kind is float:  # the common case first: this runs for every value of every map row
        return value if math.isfinite(value) else None
    if kind is int:
        return float(value)
    if value is None or isinstance(value, (bool, str)):  # noqa: UP038 - a tuple is faster than a union here
        return None
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None

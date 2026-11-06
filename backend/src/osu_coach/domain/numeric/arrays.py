"""Array-backed records: a frozen dataclass whose fields are equal-length numpy arrays, one value per item.

Used for the few domain values that hold one entry per note or key press of a replay (``HitObjects``,
``KeyPresses``, ``Events``): every field is named and typed (``notes.head_hit``), items are selected with
:meth:`ArrayRecord.take` and joined with :meth:`ArrayRecord.concat`.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Self

import numpy as np
from numpy.typing import NDArray

Floats = NDArray[np.float64]
Ints = NDArray[np.int64]
Bools = NDArray[np.bool_]
Texts = NDArray[np.object_]  # str, or None where there is no value


@dataclasses.dataclass(frozen=True, slots=True)
class ArrayRecord:
    """Base of the array-backed records. Subclasses declare their fields; ``DEFAULTS`` gives the value a field gets
    when a source has none (tests and old cache files), by field name."""

    DEFAULTS: ClassVar[Mapping[str, Any]] = {}

    def __len__(self) -> int:
        first = dataclasses.fields(self)
        return len(getattr(self, first[0].name)) if first else 0

    @classmethod
    def names(cls) -> tuple[str, ...]:
        return tuple(f.name for f in dataclasses.fields(cls))

    @classmethod
    def from_columns(cls, source: Mapping[str, Any] | Any, n: int | None = None) -> Self:
        """A record from anything indexable by field name (a mapping of sequences, or a data frame); a field the
        source lacks gets its default (``DEFAULTS``, else NaN for numbers / None for text)."""
        have = set(source.keys()) if hasattr(source, "keys") else set(source.columns)
        length = n if n is not None else (len(source) if not isinstance(source, Mapping) else _length(source))
        values = {}
        for f in dataclasses.fields(cls):
            default = cls.DEFAULTS.get(f.name, _missing(f.type))
            column = source[f.name] if f.name in have else [default] * length
            values[f.name] = _array(column, f.type, default)
        return cls(**values)

    def to_columns(self) -> dict[str, np.ndarray]:
        return {name: getattr(self, name) for name in self.names()}

    def take(self, rows: Bools | Ints | NDArray[np.intp] | slice) -> Self:
        """The items selected by a boolean mask, an index array or a slice."""
        return type(self)(**{name: getattr(self, name)[rows] for name in self.names()})

    def replace(self, **columns: Any) -> Self:
        """The record with some fields replaced (arrays, or one value for every item)."""
        n = len(self)
        out = {}
        for name, value in columns.items():
            out[name] = np.asarray(value) if np.ndim(value) else np.full(n, value, dtype=_dtype_of(value))
        return dataclasses.replace(self, **out)

    @classmethod
    def concat(cls, parts: Sequence[Self]) -> Self:
        if not parts:
            return cls.from_columns({}, n=0)
        return cls(**{name: np.concatenate([getattr(p, name) for p in parts]) for name in cls.names()})


def _length(source: Mapping[str, Any]) -> int:
    return len(next(iter(source.values()))) if source else 0


def _missing(annotation: Any) -> Any:
    text = str(annotation)
    if "Texts" in text or "object" in text:
        return None
    if "Bools" in text or "bool" in text:
        return False
    if "Ints" in text or "int64" in text:
        return 0
    return np.nan


def _array(values: Any, annotation: Any, default: Any = None) -> np.ndarray:
    text = str(annotation)
    items = values.tolist() if hasattr(values, "tolist") else list(values)
    if "Texts" in text or "object" in text:
        out = np.empty(len(items), dtype=object)
        out[:] = [None if _is_missing(v) else v for v in items]
        return out
    if "Bools" in text or "bool" in text:
        fill = bool(default) if default is not None else False
        return np.asarray([fill if _is_missing(v) else bool(v) for v in items], dtype=bool)
    if "Ints" in text or "int64" in text:
        fill = int(default) if default is not None else 0
        return np.asarray([fill if _is_missing(v) else int(v) for v in items], dtype=np.int64)
    fill = float(default) if default is not None else np.nan
    return np.asarray([fill if _is_missing(v) else float(v) for v in items], dtype=np.float64)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(value != value)  # NaN (and NA-like values that aren't equal to themselves)
    except (TypeError, ValueError):
        return True


def _dtype_of(value: Any) -> Any:
    if isinstance(value, bool | np.bool_):
        return bool
    if isinstance(value, int | np.integer):
        return np.int64
    if isinstance(value, float | np.floating):
        return np.float64
    return object

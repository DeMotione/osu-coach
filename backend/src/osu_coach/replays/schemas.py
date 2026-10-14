"""Choices of which replays to read: how many, in which time range, from where."""

from __future__ import annotations

from enum import IntEnum
from typing import Literal


class Latest(IntEnum):
    """How many of the newest replays to read; 0 = all of them."""

    newest_100 = 100
    newest_500 = 500
    newest_1000 = 1000
    all = 0


DateRange = Literal["all", "session", "7d", "30d", "custom"]


SourceMode = Literal["library", "files"]

"""Choices of which replays to read: how many, in which time range, from where."""

from __future__ import annotations

from enum import IntEnum
from typing import Literal


class Latest(IntEnum):
    """How many of the newest found replays to analyse."""

    newest_100 = 100
    newest_500 = 500
    newest_1000 = 1000


# the most replays a scan reads (newest first, per player) and an analysis takes: more took tens of minutes the first
# time and told little more about how you play now
MOST_REPLAYS = int(max(Latest))


DateRange = Literal["all", "session", "7d", "30d", "custom"]


SourceMode = Literal["library", "files"]

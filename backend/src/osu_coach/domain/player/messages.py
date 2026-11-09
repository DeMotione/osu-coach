"""What the domain tells the player, as codes: the slices word them (:mod:`osu_coach.common.texts`)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Message:
    """A message's code and the values its text shows."""

    code: str
    values: Mapping[str, Any] = field(default_factory=dict)

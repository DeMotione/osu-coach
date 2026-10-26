"""Responses of the chart-style analyses shared by several pages."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClickBand(BaseModel):
    label: str
    share: float | None


class ClickSummary(BaseModel):
    n: int
    mean_px: list[float | None] = Field(min_length=2, max_length=2, description="[x, y], osu!px.")
    mean_r: list[float | None] = Field(min_length=2, max_length=2, description="[x, y], circle radii.")
    ci_px: float | None
    sd_px: list[float | None] = Field(min_length=2, max_length=2, description="[sideways, up/down], osu!px.")
    radius: float | None
    bands: list[ClickBand]


class Clicks(BaseModel):
    """Where clicks land, in circle radii from the note centre (y down)."""

    view: Literal["screen", "movement"]
    enough: bool
    plays: int = Field(description="Plays the clicks are from.")
    n: int = Field(description="All clicks.")
    drawn: int = Field(description="Clicks in x / y (a weighted random sample).")
    x: list[float]
    y: list[float]
    hit: list[bool]
    summary: ClickSummary | None

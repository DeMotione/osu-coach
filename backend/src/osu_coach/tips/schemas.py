"""Responses of the Tips & Setup page (and the tips the Overview shows)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from osu_coach.settings.schemas import SetupModel


class TipSetting(BaseModel):
    name: str
    value: str


class SayoRow(BaseModel):
    setting: str
    now: float | bool
    suggested: float | bool
    changed: bool


class TipOut(BaseModel):
    category: str
    title: str
    severity: int = Field(ge=1, le=3, description="3 = biggest impact.")
    evidence: str
    actions: list[str]
    settings: list[TipSetting]
    sayo: list[SayoRow] | None = Field(description="SayoDevice values now → to try (Keys / SayoDevice tip).")


# ------------------------------------------------------------------ tips
class Calibration(BaseModel):
    scale: float
    step: float = Field(description="Area / sensitivity change as a fraction; 0 = keep.")
    now: str | None
    suggested: str | None
    lines: list[str]
    device: Literal["tablet", "mouse"]


class TabletArea(BaseModel):
    w: float
    h: float
    x: float | None
    y: float | None
    now_w: float
    now_h: float
    now_x: float | None
    now_y: float | None
    changed: bool
    why: list[str]


class TipsPage(BaseModel):
    setup: SetupModel
    setup_saved: bool
    calibration: Calibration | None
    tablet_area: TabletArea | None
    tips: list[TipOut]
    practice_plan: list[str]

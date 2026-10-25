"""Responses of the Tips page (and the tips the Overview shows) and of the Setup Tips page."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from osu_coach.settings.schemas import SetupModel


class TipSetting(BaseModel):
    name: str
    value: str


class TipOut(BaseModel):
    category: str
    title: str
    severity: int = Field(ge=1, le=3, description="3 = biggest impact.")
    evidence: str
    actions: list[str]
    settings: list[TipSetting]


# ------------------------------------------------------------------ tips
class TipsPage(BaseModel):
    setup: SetupModel
    setup_saved: bool
    tips: list[TipOut]
    practice_plan: list[str]


# ------------------------------------------------------------------ setup tips
class SetupChange(BaseModel):
    setting: str
    now: str | None = Field(description="The value now; null when it wasn't entered in the setup.")
    to: str = Field(description="What to set it to: a value, or a direction when the value now is unknown.")


class SetupAdvice(BaseModel):
    key: Literal["area_size", "sensitivity", "area_position", "area_rotation", "offset", "keys"]
    title: str
    verdict: Literal["change", "keep", "unknown"] = Field(
        description="change = worth changing (big enough to feel, and your misses show it costs you); keep; "
        "unknown = not enough data yet."
    )
    why: str = Field(description="One short sentence.")
    changes: list[SetupChange]
    where: str | None = Field(description="Where to change it.")


class SetupTipsPage(BaseModel):
    setup: SetupModel
    setup_saved: bool
    advice: list[SetupAdvice] = Field(description="The changes first, then what can't be told yet, then what to keep.")

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from osu_coach.domain.player.setup import Setup


class SetupModel(BaseModel):
    """The player's setup: makes the tips concrete (tablet area, sensitivity, keyboard / SayoDevice)."""

    device: Literal["tablet", "mouse"] = "tablet"
    handedness: Literal["right", "left"] = "right"
    client: Literal["stable", "lazer"] = "stable"
    area_w_mm: float | None = Field(None, ge=0, le=500)
    area_h_mm: float | None = Field(None, ge=0, le=500)
    area_x_mm: float | None = Field(None, ge=0, le=500, description="Area centre (OpenTabletDriver X).")
    area_y_mm: float | None = Field(None, ge=0, le=500, description="Area centre (OpenTabletDriver Y).")
    screen_w_px: int = Field(1920, ge=640, le=7680)
    screen_h_px: int = Field(1080, ge=480, le=4320)
    mouse_dpi: int | None = Field(None, ge=0, le=50000)
    ingame_sens: float | None = Field(None, ge=0, le=10)
    keyboard: Literal["standard", "rapid_trigger", "sayo"] = "standard"
    actuation_mm: float | None = Field(None, ge=0, le=4)
    rt_press_mm: float | None = Field(None, ge=0, le=2)
    rt_release_mm: float | None = Field(None, ge=0, le=2)
    sayo_stroke_mm: float | None = Field(None, ge=0, le=6)
    sayo_trigger_mm: float | None = Field(None, ge=0, le=6)
    sayo_release_mm: float | None = Field(None, ge=0, le=6)
    sayo_rt: bool | None = None
    sayo_rt_trigger_mm: float | None = Field(None, ge=0, le=6)
    sayo_rt_release_mm: float | None = Field(None, ge=0, le=6)
    sayo_full_stroke: bool | None = None
    sayo_rt_upper_mm: float | None = Field(None, ge=0, le=6)
    sayo_rt_lower_mm: float | None = Field(None, ge=0, le=6)

    @field_validator("area_w_mm", "area_h_mm", "mouse_dpi", "actuation_mm", "rt_press_mm", "rt_release_mm")
    @classmethod
    def _zero_is_unknown(cls, v):
        return v or None


# ------------------------------------------------------------------ tips & setup
def setup_model(setup: Setup) -> SetupModel:
    try:
        return SetupModel.model_validate(asdict(setup))
    except ValidationError:  # a value out of range in an old settings file: shown as it is
        return SetupModel.model_construct(**asdict(setup))

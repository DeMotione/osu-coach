"""The player's setup (device, tablet area, sensitivity, keyboard) as entered in the app; the tips engine reads it."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Setup:
    device: str = "tablet"            # tablet | mouse
    handedness: str = "right"         # right | left
    area_w_mm: float | None = None
    area_h_mm: float | None = None
    area_x_mm: float | None = None    # area centre on the tablet (OpenTabletDriver X / Y)
    area_y_mm: float | None = None
    screen_w_px: int = 1920
    screen_h_px: int = 1080
    mouse_dpi: int | None = None
    ingame_sens: float | None = None  # osu! sensitivity multiplier
    keyboard: str = "standard"        # standard | rapid_trigger | sayo
    actuation_mm: float | None = None
    rt_press_mm: float | None = None
    rt_release_mm: float | None = None
    # SayoDevice keypad (names as in its web configurator); None = not entered
    sayo_stroke_mm: float | None = None
    sayo_trigger_mm: float | None = None
    sayo_release_mm: float | None = None
    sayo_rt: bool | None = None
    sayo_rt_trigger_mm: float | None = None
    sayo_rt_release_mm: float | None = None
    sayo_full_stroke: bool | None = None
    sayo_rt_upper_mm: float | None = None
    sayo_rt_lower_mm: float | None = None
    client: str = "stable"            # stable | lazer

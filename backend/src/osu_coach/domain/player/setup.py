"""The player's setup (device, tablet area, sensitivity, keyboard) as entered in the app; the tips engine reads it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Setup:
    device: str = "tablet"  # tablet | mouse
    handedness: str = "right"  # right | left
    area_w_mm: float | None = None
    area_h_mm: float | None = None
    area_x_mm: float | None = None  # area centre on the tablet (OpenTabletDriver X / Y)
    area_y_mm: float | None = None
    screen_w_px: int = 1920
    screen_h_px: int = 1080
    mouse_dpi: int | None = None
    ingame_sens: float | None = None  # osu! sensitivity multiplier
    keyboard: str = "standard"  # standard | rapid_trigger | sayo
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
    client: str = "stable"  # stable | lazer


# The settings each group of setup checks reads. Once one of them is changed on the device, the group's checks wait for
# plays made with the new value (#131). The audio offset is set in osu!, not here, so its check reads every play.
CHECKED_BY = {
    "aim": (
        "device", "area_w_mm", "area_h_mm", "area_x_mm", "area_y_mm", "screen_w_px", "screen_h_px", "mouse_dpi",
        "ingame_sens",
    ),
    "keys": (
        "keyboard", "actuation_mm", "rt_press_mm", "rt_release_mm", "sayo_stroke_mm", "sayo_trigger_mm",
        "sayo_release_mm", "sayo_rt", "sayo_rt_trigger_mm", "sayo_rt_release_mm", "sayo_full_stroke",
        "sayo_rt_upper_mm", "sayo_rt_lower_mm",
    ),
}  # fmt: skip


def _replaced(old: object, new: object) -> bool:
    return old is not None and new is not None and old != new


def changed_groups(old: Setup, new: Setup) -> set[str]:
    """The groups of settings (:data:`CHECKED_BY`) changed on the device between two saves: a value replaced by
    another. A value entered where there was none, or cleared, describes the setup; it doesn't change it."""
    return {g for g, names in CHECKED_BY.items() if any(_replaced(getattr(old, n), getattr(new, n)) for n in names)}

"""Tips engine: turns a replay profile + the player's setup into concrete advice.

Every tip carries the evidence (numbers measured from the replays) and concrete
actions, and — where the data supports it — exact settings to try (tablet area,
mouse sensitivity, rapid-trigger values). Rules of thumb used:

* tablet area: overaim -> area too small (too sensitive) -> enlarge; underaim ->
  shrink; change in small steps (5-10 %) and keep a setting for days
  (osu! community guides, rgbeing's aim-analyzer cheat-sheet for
  skew/scale/rotation);
* rapid trigger (hall-effect keyboards): osu! players typically sit around
  0.3-1.0 mm actuation with 0.1-0.3 mm RT sensitivity; very low values (0.1 mm)
  cause chatter / accidental double taps, too high values miss fast taps.
"""

from __future__ import annotations

from osu_coach.tips.domain.common import Tip
from osu_coach.tips.domain.engine import make_tips, practice_plan
from osu_coach.tips.domain.keyboard import rt_baseline, sayo_settings
from osu_coach.tips.domain.tablet import aim_calibration, mm_per_osu_px, suggest_tablet_area

__all__ = [
    "Tip",
    "aim_calibration",
    "make_tips",
    "mm_per_osu_px",
    "practice_plan",
    "rt_baseline",
    "sayo_settings",
    "suggest_tablet_area",
]

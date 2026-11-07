"""Stamina: the tempo the player keeps up over time (the tempo-duration curve the stamina rating uses)."""

from __future__ import annotations

STAMINA_REACH = 10  # BPM above the clean stream speed that still counts as reachable (precision chart)
STAMINA_KEPT = 0.9  # share of a stream's notes you must have pressed for: "your fingers kept going"
STAMINA_KEPT_ZERO = 0.6  # ... below this share a stream adds nothing; in between it counts partly
# stamina = the tempo you keep up for a given time (tempo-duration curve):
STAMINA_WINDOWS = (10, 30, 60, 120, 300)  # seconds
PRESSED_REASONS = ("early", "late", "aim", "notelock")  # misses where a key was pressed

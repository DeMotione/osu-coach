"""Reading (AR / BPM changes): metrics and the per-play values the reading rating uses."""

from __future__ import annotations

import numpy as np

# ------------------------------------------------------------------ reading
READ_AR_STEP = 3.0  # every 3 AR below what is usual for the map's star rating doubles the reading demand
READ_AR_MIN = 1.0  # the AR factor never lowers the value
READ_AR_HIGH_STEP = 1.5  # every 1.5 AR above the usual AR doubles it too (reaction to fast approach)
READ_NPS = 5.0  # circles per second (during play, breaks left out) at which low AR counts fully ...
READ_NPS_RANGE = (0.25, 2.0)  # ... the AR difference counts × circles per second ÷ 5 (0.25–2)
READ_HD, READ_FL = 1.2, 1.6  # hidden / flashlight hide the notes: more to read
READ_BPM_JUMP = 0.08  # a BPM change: the beat length changes by 8%+ from one note to the next
READ_BPM_NOTES = 4  # the first 4 notes after a BPM change show whether you read it
READ_BPM_FULL = 8  # 8+ BPM changes in a map = the full BPM-change bonus (×1.5 when you hit them as 300s)
READ_BPM_BONUS = 0.5
READ_ACC_POWER = 8.0  # × accuracy^8: 99% = 0.92, 95% = 0.66, 90% = 0.43, 85% = 0.27


def usual_ar(stars) -> np.ndarray:
    """The approach rate maps of this star rating (with mods) usually have: 7.25 at 3*, 9.5 at 6*, 10.5 from 7.3*."""
    return np.clip(5.0 + 0.75 * np.asarray(stars, dtype=float), 5.0, 10.5)

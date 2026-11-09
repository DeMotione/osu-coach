"""Skill names and the thresholds the profile modules share (the texts the pages show are in
:mod:`osu_coach.common.texts`)."""

from __future__ import annotations

SKILLS = ("aim", "flow_aim", "speed", "stamina", "accuracy", "sliders", "reading", "consistency")
FAST_JUMP_MS = 125.0  # jumps this close in time (1/2 at 240 BPM, real time) are "very fast"

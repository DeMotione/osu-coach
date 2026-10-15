"""The :class:`Profile`: what the analysis pages read."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Profile:
    overview: dict
    replays: pd.DataFrame
    miss_breakdown: dict
    slider_breaks: dict
    tapping: dict
    stream_profile: pd.DataFrame
    aim: dict
    quadrants: pd.DataFrame
    worst_quadrant: dict | None
    grid: pd.DataFrame
    directions: pd.DataFrame
    distances: pd.DataFrame
    angles: pd.DataFrame
    regression: dict | None
    sliders: dict
    reading: dict
    consistency: dict
    skills: dict
    strengths: list
    weaknesses: list
    levels: dict
    objects: pd.DataFrame = field(repr=False)
    presses: pd.DataFrame = field(repr=False)
    model: object = field(default=None, repr=False)  # miss chance by local difficulty (fit_miss_model)
    miss_breakdown_raw: dict = field(default_factory=dict)  # the same, unweighted counts
    fall_behind: dict = field(default_factory=dict)  # stream_fall_behind()
    experimental_skills: dict = field(default_factory=dict)  # Lab comfort-relative abilities

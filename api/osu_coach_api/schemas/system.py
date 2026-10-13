from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .common import Choice


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    core_version: str
    web_app: bool = Field(description="Whether the built web app is served at /.")
    data_dir: str = Field(description="osu! coach data folder: settings, analysis cache, progress.")


class SkillMeta(BaseModel):
    key: str
    label: str
    what: str = Field(description="What the skill measures.")
    how: str = Field(description="How the score is worked out.")
    practise: str = Field(description="What raises it.")


class MissCauseMeta(BaseModel):
    key: str
    description: str


class Meta(BaseModel):
    """Labels and choices shared by every page."""
    version: str
    skills: list[SkillMeta]
    playlist_skills: list[Choice]
    miss_causes: list[MissCauseMeta]
    date_choices: list[Choice]
    replay_sets: list[Choice]
    best_definition: str
    latest_choices: list[int] = Field(description="Replay counts to read; 0 = all.")
    periods: list[str]
    lazer_instructions: list[str] = Field(description="Steps to import a lazer import folder (Markdown).")
    level_band: float
    level_sigma: float

"""The player's setup as the API shows it."""
from __future__ import annotations

import os
from dataclasses import asdict

from pydantic import ValidationError

from osu_coach.settings.domain import Setup

from osu_coach.settings.schemas import SetupModel


# ------------------------------------------------------------------ tips & setup
def setup_model(setup: Setup) -> SetupModel:
    try:
        return SetupModel.model_validate(asdict(setup))
    except ValidationError:     # a value out of range in an old settings file: shown as it is
        return SetupModel.model_construct(**asdict(setup))


def default_folders(settings: dict) -> str:
    return settings.get("folders") or os.environ.get("OSU_COACH_DEMO", "")

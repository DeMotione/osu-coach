"""Health and the labels and choices every page shares."""

from __future__ import annotations

from pathlib import Path

from osu_coach import __version__
from osu_coach.common.schemas import Choice
from osu_coach.common.texts import MISS_LABELS, SKILL_HELP, SKILL_LABELS
from osu_coach.domain.maps.suggestions import PLAYLIST_SKILLS, skill_label
from osu_coach.domain.player import LEVEL_BAND, LEVEL_SIGMA
from osu_coach.domain.progress.periods import PERIODS
from osu_coach.domain.replays import scope
from osu_coach.domain.replays.selection import Latest
from osu_coach.features.system.schemas import Health, Meta, MissCauseMeta, SkillMeta
from osu_coach.infra.exports import lazer_import

LATEST_CHOICES = [int(c) for c in Latest]


def health(web_app: bool, data_dir: Path) -> Health:
    return Health(version=__version__, core_version=__version__, web_app=web_app, data_dir=str(data_dir))


def meta(api_docs: bool) -> Meta:
    return Meta(
        api_docs=api_docs,
        version=__version__,
        skills=[
            SkillMeta(key=k, label=label, what=SKILL_HELP[k][0], how=SKILL_HELP[k][1], practise=SKILL_HELP[k][2])
            for k, label in SKILL_LABELS.items()
        ],
        playlist_skills=[Choice(key=k, label=skill_label(k)) for k in PLAYLIST_SKILLS],
        miss_causes=[MissCauseMeta(key=k, description=v) for k, v in MISS_LABELS.items()],
        date_choices=[Choice(key=k, label=scope.DATE_LABELS[k]) for k in scope.DATE_CHOICES],
        replay_sets=[Choice(key=k, label=scope.REPLAY_SET_LABELS[k]) for k in scope.REPLAY_SETS],
        best_definition=scope.BEST_DEFINITION,
        latest_choices=LATEST_CHOICES,
        periods=list(PERIODS),
        lazer_instructions=list(lazer_import.INSTRUCTIONS),
        level_band=LEVEL_BAND,
        level_sigma=LEVEL_SIGMA,
    )

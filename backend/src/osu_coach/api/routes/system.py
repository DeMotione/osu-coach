from __future__ import annotations

from fastapi import APIRouter, Request

from osu_coach.infrastructure.filesystem import lazer_import
from osu_coach.domain import selection
from osu_coach.domain.progress import PERIODS
from osu_coach.domain.map_recommendations import SKILLS, skill_label
from osu_coach.domain.profile import LEVEL_BAND, LEVEL_SIGMA, MISS_LABELS, SKILL_HELP, SKILL_LABELS

from osu_coach import __version__
from osu_coach.api.deps import WorkspaceDep
from osu_coach.api.schemas.common import Choice
from osu_coach.api.schemas.system import Health, Meta, MissCauseMeta, SkillMeta

router = APIRouter(tags=["System"])
LATEST_CHOICES = [100, 500, 1000, 0]


@router.get("/health", summary="Is the API up")
def health(request: Request, ws: WorkspaceDep) -> Health:
    return Health(version=__version__, core_version=__version__,
                  web_app=request.app.state.web_dir is not None, data_dir=str(ws.cache_dir))


@router.get("/meta", summary="Labels and choices shared by every page")
def meta(request: Request) -> Meta:
    return Meta(
        api_docs=request.app.state.api_docs,
        version=__version__,
        skills=[SkillMeta(key=k, label=label, what=SKILL_HELP[k][0], how=SKILL_HELP[k][1], practise=SKILL_HELP[k][2])
                for k, label in SKILL_LABELS.items()],
        playlist_skills=[Choice(key=k, label=skill_label(k)) for k in SKILLS + ["quadrant", "general"]],
        miss_causes=[MissCauseMeta(key=k, description=v) for k, v in MISS_LABELS.items()],
        date_choices=[Choice(key=k, label=selection.DATE_LABELS[k]) for k in selection.DATE_CHOICES],
        replay_sets=[Choice(key=k, label=selection.REPLAY_SET_LABELS[k]) for k in selection.REPLAY_SETS],
        best_definition=selection.BEST_DEFINITION, latest_choices=LATEST_CHOICES, periods=list(PERIODS),
        lazer_instructions=list(lazer_import.INSTRUCTIONS), level_band=LEVEL_BAND, level_sigma=LEVEL_SIGMA)

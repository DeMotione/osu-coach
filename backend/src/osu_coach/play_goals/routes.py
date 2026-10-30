from fastapi import APIRouter

from osu_coach.app.deps import WorkspaceDep
from osu_coach.app.errors import responses
from osu_coach.jobs.schemas import job_view
from osu_coach.play_goals import service
from osu_coach.play_goals.schemas import PlayGoalJob, PlayGoalOptions, PlayGoalRequest

router = APIRouter(prefix="/play-goals", tags=["Play Goals"])


@router.get("", summary="Remembered play goal and local evidence coverage", responses=responses(422, 503))
def options(ws: WorkspaceDep) -> PlayGoalOptions:
    return service.options(ws)


@router.post("", status_code=202, summary="Assess a goal and find your next plays", responses=responses(409, 422, 503))
def evaluate(request: PlayGoalRequest, ws: WorkspaceDep) -> PlayGoalJob:
    service.validate_request(ws, request)
    return job_view(
        PlayGoalJob,
        ws.jobs.start(
            "play_goal", "Play Goals", lambda report: service.evaluate(ws, request, report), cancellable=True
        ),
    )

"""FastAPI dependencies."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from osu_coach.profile.domain import Profile

from osu_coach.app.workspace import Workspace


def get_workspace(request: Request) -> Workspace:
    return request.app.state.workspace


def get_profile(ws: Annotated[Workspace, Depends(get_workspace)]) -> Profile:
    """The current profile; 409 ``no_profile`` before anything was analysed."""
    return ws.require_profile()


WorkspaceDep = Annotated[Workspace, Depends(get_workspace)]
ProfileDep = Annotated[Profile, Depends(get_profile)]


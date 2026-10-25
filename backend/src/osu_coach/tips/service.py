"""The Tips page (tips and the practice plan) and the Setup Tips page (what to change in the setup)."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

from osu_coach.profile.domain import Profile
from osu_coach.settings.service import setup_model
from osu_coach.tips import schemas as S
from osu_coach.tips.domain import Tip, make_tips, practice_plan, setup_advice

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace


# ------------------------------------------------------------------ tips
def tip_out(t: Tip) -> S.TipOut:
    settings = (
        []
        if t.settings is None
        else [S.TipSetting(name=k, value=str(v)) for k, v in t.settings.items() if v is not None]
    )
    return S.TipOut(
        category=t.category,
        title=t.title,
        severity=int(t.severity),
        evidence=t.evidence,
        actions=list(t.actions),
        settings=settings,
    )


def tips(ws: Workspace, p: Profile) -> list[Tip]:
    setup = ws.setup()
    key = "tips:" + repr(sorted(asdict(setup).items()))
    return ws.memo(key, lambda: make_tips(p, setup))


def tips_page(ws: Workspace, p: Profile) -> S.TipsPage:
    return S.TipsPage(
        setup=setup_model(ws.setup()),
        setup_saved=bool(ws.settings().get("setup_saved")),
        tips=[tip_out(t) for t in tips(ws, p)],
        practice_plan=list(practice_plan(p)),
    )


# ------------------------------------------------------------------ setup tips
def setup_tips_page(ws: Workspace, p: Profile) -> S.SetupTipsPage:
    setup = ws.setup()
    key = "setup-tips:" + repr(sorted(asdict(setup).items()))
    advice = ws.memo(key, lambda: setup_advice(p, setup))
    return S.SetupTipsPage(
        setup=setup_model(setup),
        setup_saved=bool(ws.settings().get("setup_saved")),
        advice=[
            S.SetupAdvice(
                key=a.key,
                title=a.title,
                verdict=a.verdict,
                why=a.why,
                changes=[S.SetupChange(setting=c.setting, now=c.now, to=c.to) for c in a.changes],
                where=a.where,
            )
            for a in advice
        ],
    )

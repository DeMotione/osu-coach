"""The Tips page (tips and the practice plan) and the Setup Tips page (what to change in the setup)."""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict
from typing import TYPE_CHECKING

from osu_coach.common.setup import setup_model
from osu_coach.domain.player import Profile, profile_for
from osu_coach.domain.player.setup import CHECKED_BY
from osu_coach.features.tips import schemas as S
from osu_coach.features.tips.rules import Since, Tip, make_tips, practice_plan, setup_advice
from osu_coach.infra import clock

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
        setup_saved=bool(ws.settings().setup_saved),
        tips=[tip_out(t) for t in tips(ws, p)],
        practice_plan=list(practice_plan(p)),
    )


# ------------------------------------------------------------------ setup tips
def _utc(t: dt.datetime) -> dt.datetime:
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)  # a replay's time is UTC


def _since(ws: Workspace, changed: dict[str, dt.datetime]) -> dict[str, Since]:
    """The groups of settings changed in Your setup, each with the profile of the plays made since (#131)."""
    s = ws.settings()
    out = {}
    for group, when in changed.items():
        if group not in CHECKED_BY:
            continue
        plays = [pl for pl in ws.plays if pl.meta.date is not None and _utc(pl.meta.date) >= when]
        later = profile_for(plays, s.replay_set or "all", ws.rating_engine(), s.level_override) if plays else None
        out[group] = Since(when.astimezone(clock.local_tz()).date(), later)
    return out


def setup_tips_page(ws: Workspace, p: Profile) -> S.SetupTipsPage:
    setup = ws.setup()
    changed = ws.settings().setup_changed
    key = "setup-tips:" + repr(sorted(asdict(setup).items())) + repr(sorted(changed.items()))
    advice = ws.memo(key, lambda: setup_advice(p, setup, _since(ws, changed)))
    return S.SetupTipsPage(
        setup=setup_model(setup),
        setup_saved=bool(ws.settings().setup_saved),
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

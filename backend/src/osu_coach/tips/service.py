"""The tips page: tips, calibration and the practice plan."""
from __future__ import annotations

from typing import TYPE_CHECKING

from dataclasses import asdict


from osu_coach.tips.domain import Tip, aim_calibration, make_tips, practice_plan, sayo_settings, suggest_tablet_area
from osu_coach.settings.domain import Setup
from osu_coach.profile.domain import Profile

from osu_coach.tips import schemas as S
from osu_coach.settings.service import setup_model

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace


# ------------------------------------------------------------------ tips
def _setting_value(v) -> str:
    return str(v)


def tip_out(t: Tip, p: Profile | None = None, setup: Setup | None = None) -> S.TipOut:
    sayo = None
    if t.category == "Keys / SayoDevice" and p is not None and setup is not None:
        r = sayo_settings(p, setup)
        sayo = [S.SayoRow(setting=k, now=r["now"][k], suggested=r["new"][k], changed=r["new"][k] != r["now"][k])
                for k in r["now"]]
    settings = [] if t.settings is None or t.category == "Keys / SayoDevice" else [
        S.TipSetting(name=k, value=_setting_value(v)) for k, v in t.settings.items() if v is not None]
    return S.TipOut(category=t.category, title=t.title, severity=int(t.severity), evidence=t.evidence,
                    actions=list(t.actions), settings=settings, sayo=sayo)


def tips(ws: Workspace, p: Profile) -> list[Tip]:
    setup = ws.setup()
    key = "tips:" + repr(sorted(asdict(setup).items()))
    return ws.memo(key, lambda: make_tips(p, setup))


def tips_page(ws: Workspace, p: Profile) -> S.TipsPage:
    setup = ws.setup()
    c = aim_calibration(p, setup)
    calibration = None
    if c:
        calibration = S.Calibration(scale=float(c["scale"]), step=float(c["step"]), now=c["now"], suggested=c["try"],
                                    lines=list(c["lines"]), device=c["device"])
    area = suggest_tablet_area(p, setup)
    tablet_area = None
    if area:
        tablet_area = S.TabletArea(w=area["w"], h=area["h"], x=area["x"], y=area["y"], now_w=area["now"]["w"],
                                   now_h=area["now"]["h"], now_x=area["now"]["x"], now_y=area["now"]["y"],
                                   changed=bool(area["changed"]), why=list(area["why"]))
    return S.TipsPage(setup=setup_model(setup), setup_saved=bool(ws.settings().get("setup_saved")),
                      calibration=calibration, tablet_area=tablet_area,
                      tips=[tip_out(t, p, setup) for t in tips(ws, p)], practice_plan=list(practice_plan(p)))

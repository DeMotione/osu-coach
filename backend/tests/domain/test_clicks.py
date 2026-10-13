"""'Where your clicks land' (Aim page): the on-screen view must show what the jump-rotated view
can't (a constant offset), and the numbers must count clicks outside the circle."""
import numpy as np
import pandas as pd
import pytest

from osu_coach.domain.analysis import along_cross
from osu_coach.domain.profile import click_points, click_summary

R = 36.5


def _objects(n=600, dx=6.0, dy=-3.0, sd=8.0, aim_misses=0, seed=1):
    """Jumps in every direction; clicks land (dx, dy) px off the centre on average."""
    rng = np.random.default_rng(seed)
    ang = rng.uniform(0, 2 * np.pi, n)
    dist = rng.uniform(120, 300, n)
    sx, sy = 256 - np.cos(ang) * dist / 2, 192 - np.sin(ang) * dist / 2
    x, y = sx + np.cos(ang) * dist, sy + np.sin(ang) * dist
    ex = dx + rng.normal(0, sd, n)
    ey = dy + rng.normal(0, sd, n)
    hit = np.ones(n, bool)
    reason = np.array([None] * n, dtype=object)
    for i in range(aim_misses):            # clicks 1.3 radii away in a random direction
        a = rng.uniform(0, 2 * np.pi)
        ex[i], ey[i] = np.cos(a) * 1.3 * R, np.sin(a) * 1.3 * R
        hit[i], reason[i] = False, "aim"
    ac = [along_cross(a, b, c, d) for a, b, c, d in zip(ex, ey, x - sx, y - sy)]
    return pd.DataFrame({
        "played": True, "kind": "circle", "head_hit": hit, "miss_reason": reason, "x": x, "y": y,
        "err_dx": ex, "err_dy": ey, "radius": R, "dist_norm": dist / (2 * R),
        "along": [a / R for a, _ in ac], "cross": [c / R for _, c in ac],
    })


def test_screen_view_shows_a_constant_offset_the_jump_view_cancels():
    O = _objects(dx=6.0, dy=-3.0)
    s = click_summary(click_points(O, "screen"))
    assert s["mean_px"] == pytest.approx((6.0, -3.0), abs=1.0)
    assert s["ci_px"] < 1.0
    move = click_points(O, "movement")
    # rotated so every jump goes right: the same 6 px offset averages out to ~0
    assert abs(move["x"].mean()) < 0.05 and abs(move["y"].mean()) < 0.05


def test_clicks_outside_the_circle_are_counted():
    O = _objects(n=100, dx=0, dy=0, sd=5, aim_misses=10)
    s = click_summary(click_points(O, "screen"))
    assert s["n"] == 100
    assert s["outside"] == pytest.approx(0.10)
    assert sum(s["bands"].values()) == pytest.approx(1.0)


def test_misses_without_a_click_are_not_plotted():
    O = _objects(n=50)
    O.loc[:4, "head_hit"] = False
    O.loc[:4, "miss_reason"] = "lost"         # no click near the note at all
    O.loc[5:9, "dist_norm"] = 0.4             # stream notes: in the screen view, not in the jump view
    assert len(click_points(O, "screen")) == 45
    assert len(click_points(O, "movement")) == 40

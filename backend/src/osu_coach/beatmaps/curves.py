"""Slider path approximation, ported from osu!lazer's PathApproximator / SliderPath.

Produces a polyline, then trims or extends it to the slider's expected pixel length
exactly like lazer (and stable) do.
"""

from __future__ import annotations

import bisect
import math

BEZIER_TOLERANCE = 0.25
CIRCULAR_ARC_TOLERANCE = 0.1
CATMULL_DETAIL = 50

Point = tuple[float, float]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _mul(a, s):
    return (a[0] * s, a[1] * s)


def _len(a):
    return math.hypot(a[0], a[1])


# ---------------------------------------------------------------- bezier
def _is_flat_enough(points) -> bool:
    tol = BEZIER_TOLERANCE * BEZIER_TOLERANCE * 4
    for i in range(1, len(points) - 1):
        p0, p1, p2 = points[i - 1], points[i], points[i + 1]
        dx = p0[0] - 2 * p1[0] + p2[0]
        dy = p0[1] - 2 * p1[1] + p2[1]
        if dx * dx + dy * dy > tol:
            return False
    return True


def _subdivide(points, left, right, mid, count):
    for i in range(count):
        mid[i] = points[i]
    for i in range(count):
        left[i] = mid[0]
        right[count - i - 1] = mid[count - i - 1]
        for j in range(count - i - 1):
            a, b = mid[j], mid[j + 1]
            mid[j] = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _approximate(points, buf1, buf2, count, output):
    left, right = buf2, buf1
    _subdivide(points, left, right, buf1, count)
    for i in range(count - 1):
        left[count + i] = right[i + 1]
    output.append(points[0])
    for i in range(1, count - 1):
        idx = 2 * i
        a, b, c = left[idx - 1], left[idx], left[idx + 1]
        output.append((0.25 * (a[0] + 2 * b[0] + c[0]), 0.25 * (a[1] + 2 * b[1] + c[1])))


def approximate_bezier(control_points: list[Point]) -> list[Point]:
    count = len(control_points)
    out: list[Point] = []
    if count == 0:
        return out
    if count == 1:
        return [control_points[0]]
    buf1: list = [None] * count
    buf2: list = [None] * (count * 2 - 1)
    to_flatten = [list(control_points)]
    free = []
    left_child = buf2
    guard = 0
    while to_flatten:
        guard += 1
        if guard > 200000:  # pathological control points; bail out safely
            break
        parent = to_flatten.pop()
        if _is_flat_enough(parent):
            _approximate(parent, buf1, buf2, count, out)
            free.append(parent)
            continue
        right_child = free.pop() if free else [None] * count
        _subdivide(parent, left_child, right_child, buf1, count)
        for i in range(count):
            parent[i] = left_child[i]
        to_flatten.append(right_child)
        to_flatten.append(parent)
    out.append(control_points[-1])
    return out


# ---------------------------------------------------------------- perfect circle
def approximate_circular_arc(points: list[Point]) -> list[Point] | None:
    a, b, c = points
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-3:
        return None  # collinear -> caller falls back to bezier
    a_sq = a[0] ** 2 + a[1] ** 2
    b_sq = b[0] ** 2 + b[1] ** 2
    c_sq = c[0] ** 2 + c[1] ** 2
    centre = (
        (a_sq * (b[1] - c[1]) + b_sq * (c[1] - a[1]) + c_sq * (a[1] - b[1])) / d,
        (a_sq * (c[0] - b[0]) + b_sq * (a[0] - c[0]) + c_sq * (b[0] - a[0])) / d,
    )
    da, dc = _sub(a, centre), _sub(c, centre)
    r = _len(da)
    theta_start = math.atan2(da[1], da[0])
    theta_end = math.atan2(dc[1], dc[0])
    while theta_end < theta_start:
        theta_end += 2 * math.pi
    direction = 1
    theta_range = theta_end - theta_start
    ortho_ac = (c[1] - a[1], -(c[0] - a[0]))
    if ortho_ac[0] * (b[0] - a[0]) + ortho_ac[1] * (b[1] - a[1]) < 0:
        direction = -1
        theta_range = 2 * math.pi - theta_range
    if 2 * r <= CIRCULAR_ARC_TOLERANCE:
        amount = 2
    else:
        amount = max(2, math.ceil(theta_range / (2 * math.acos(max(-1.0, 1 - CIRCULAR_ARC_TOLERANCE / r)))))
    amount = min(amount, 1000)
    out = []
    for i in range(amount):
        frac = i / (amount - 1)
        theta = theta_start + direction * frac * theta_range
        out.append((centre[0] + math.cos(theta) * r, centre[1] + math.sin(theta) * r))
    return out


# ---------------------------------------------------------------- catmull
def _catmull(v1, v2, v3, v4, t):
    t2, t3 = t * t, t * t * t
    return tuple(
        0.5
        * (
            2 * v2[k]
            + (-v1[k] + v3[k]) * t
            + (2 * v1[k] - 5 * v2[k] + 4 * v3[k] - v4[k]) * t2
            + (-v1[k] + 3 * v2[k] - 3 * v3[k] + v4[k]) * t3
        )
        for k in range(2)
    )


def approximate_catmull(points: list[Point]) -> list[Point]:
    out = []
    n = len(points)
    for i in range(n - 1):
        v1 = points[i - 1] if i > 0 else points[i]
        v2 = points[i]
        v3 = points[i + 1] if i < n - 1 else _sub(_mul(v2, 2), v1)
        v4 = points[i + 2] if i < n - 2 else _sub(_mul(v3, 2), v2)
        for c in range(CATMULL_DETAIL):
            out.append(_catmull(v1, v2, v3, v4, c / CATMULL_DETAIL))
            out.append(_catmull(v1, v2, v3, v4, (c + 1) / CATMULL_DETAIL))
    return out


def _approximate_segment(kind: str, pts: list[Point]) -> list[Point]:
    if len(pts) < 2:
        return list(pts)
    if kind == "L":
        return list(pts)
    if kind == "P" and len(pts) == 3:
        arc = approximate_circular_arc(pts)
        if arc is not None:
            return arc
    if kind == "C":
        return approximate_catmull(pts)
    return approximate_bezier(pts)


class SliderPath:
    """Polyline path of a slider with lazer-compatible length handling.

    ``control_points`` are absolute coordinates (first one = slider head).
    ``point_types`` optionally gives a curve type at a control point index,
    which starts a new segment there (lazer multi-segment format).
    """

    def __init__(
        self,
        curve_type: str,
        control_points: list[Point],
        expected_length: float | None,
        point_types: dict[int, str] | None = None,
    ):
        self.points: list[Point] = []
        self.cumulative: list[float] = [0.0]
        self._build(curve_type, list(control_points), dict(point_types or {}))
        self._calculate_length(expected_length)

    def _build(self, curve_type: str, cps: list[Point], point_types: dict[int, str]):
        if not cps:
            self.points = [(0.0, 0.0)]
            return
        # Legacy red anchors: a repeated point ends the current segment; the
        # duplicate is dropped and the segment type carries on.
        pts: list[Point] = []
        types: list[str | None] = []
        cur = curve_type
        for i, p in enumerate(cps):
            t = point_types.get(i)
            if i == 0:
                t = t or curve_type
            if t:
                cur = t
            if pts and p == pts[-1]:
                if types[-1] is None:
                    types[-1] = cur
                continue
            pts.append(p)
            types.append(t)
        types[0] = types[0] or curve_type
        bounds = [i for i, t in enumerate(types) if t] + [len(pts) - 1]
        out: list[Point] = []
        for k in range(len(bounds) - 1):
            a, b = bounds[k], bounds[k + 1]
            if b <= a:
                continue
            seg = pts[a : b + 1]
            for p in _approximate_segment(types[a], seg):
                if not out or out[-1] != p:
                    out.append(p)
        self.points = out or [pts[0]]

    def _calculate_length(self, expected: float | None):
        pts = self.points
        cum = [0.0]
        total = 0.0
        for i in range(len(pts) - 1):
            total += _len(_sub(pts[i + 1], pts[i]))
            cum.append(total)
        if expected is not None and expected >= 0 and abs(total - expected) > 1e-9:
            if len(pts) >= 2 and pts[-1] == pts[-2] and expected > total:
                self.cumulative = cum
                return
            cum.pop()
            end_index = len(pts) - 1
            if total > expected:
                while cum and cum[-1] >= expected:
                    cum.pop()
                    pts.pop()
                    end_index -= 1
            if end_index <= 0:
                self.points = pts[:1] or [(0.0, 0.0)]
                self.cumulative = [0.0]
                return
            d = _sub(pts[end_index], pts[end_index - 1])
            ln = _len(d)
            direction = (d[0] / ln, d[1] / ln) if ln > 0 else (0.0, 0.0)
            pts[end_index] = _add(pts[end_index - 1], _mul(direction, expected - cum[-1]))
            cum.append(expected)
        self.points = pts
        self.cumulative = cum

    @property
    def length(self) -> float:
        return self.cumulative[-1]

    def position_at(self, progress: float) -> Point:
        """progress 0..1 along the (trimmed/extended) path."""
        if len(self.points) == 1 or self.length <= 0:
            return self.points[0]
        d = min(max(progress, 0.0), 1.0) * self.length
        i = bisect.bisect_left(self.cumulative, d)
        if i <= 0:
            return self.points[0]
        if i >= len(self.points):
            return self.points[-1]
        p0, p1 = self.points[i - 1], self.points[i]
        d0, d1 = self.cumulative[i - 1], self.cumulative[i]
        if d1 - d0 <= 1e-12:
            return p0
        w = (d - d0) / (d1 - d0)
        return (p0[0] + (p1[0] - p0[0]) * w, p0[1] + (p1[1] - p0[1]) * w)

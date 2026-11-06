"""Fitting the abilities: MAP of the skills, the session drop and the lapse rate, and accuracy on its own.

Spec and why it differs from it: docs/star-scale-irt.md.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from osu_coach.domain.numeric.stats import weighted_quantile
from osu_coach.domain.player.engines.irt import constants as K
from osu_coach.domain.player.engines.irt.items import IrtGroups

N_SKILLS = len(K.SKILLS)
LOG_TINY = math.log(1e-12)
STARTS = (0.0, -2.0, 2.0)  # ★ from the prior centre, plus a start at each skill's typical difficulty
SENSITIVITY = 1.0  # ★: the prior centre is moved this far either way to see how much the answer follows it
BAND, BAND_ITEMS = 0.5, 30.0  # ★ wide bands, and the items one needs to count as held
GUARD = 60.0  # ★ from the prior centre: a fit that runs further has failed (a guard, never a score)


@dataclass(frozen=True, slots=True)
class SkillFit:
    """One skill: ability (★), SE, items, hardest difficulty tested, plays, other near-equal answers."""

    theta: float
    se: float
    items: float
    tested: float
    plays: float = 0.0
    modes: tuple[float, float] | None = None
    prior_shift: float = 0.0


@dataclass(frozen=True, slots=True)
class IrtFit:
    """The fit of every skill, the session drop δ, the lapse rate ε and the prior centre."""

    skills: dict[str, SkillFit]
    delta: float
    delta_se: float
    eps: float
    prior: float
    converged: bool
    loglik: float = math.nan
    message: str = ""
    cov: np.ndarray | None = field(default=None, repr=False)  # of the six skills' θ (with the design effect)


# ------------------------------------------------------------------ the joint likelihood
@dataclass(frozen=True, slots=True)
class _Data:
    b: np.ndarray  # G × 6, 0 where not tested
    mask: np.ndarray  # G × 6
    a: np.ndarray  # G × 6: each group's discrimination per skill
    c: np.ndarray  # G: logit of the share held at θ = b
    late: np.ndarray
    n: np.ndarray
    f: np.ndarray  # G × 3
    mix: np.ndarray  # 1 for head groups (miss classes and random lapses), 0 for sliders and timing


def _data(groups: IrtGroups) -> _Data:
    g = _data_groups(groups)
    b = g.b()
    mask = np.isfinite(b)
    f = np.column_stack([g.f_a, g.f_b, g.f_t])
    timing = g.kind == K.TIMING
    a = np.where(timing[:, None], K.A_TIMING, K.A[None, :]) * np.ones_like(b)
    c = np.where(timing, K.C_TIMING, K.C)
    mix = (g.kind == K.HEAD).astype(float)
    return _Data(np.where(mask, b, 0.0), mask, a, c, g.late.astype(float), g.n.astype(float), f, mix)


def _data_groups(groups: IrtGroups) -> IrtGroups:
    return groups.take(groups.kind != K.ACCURACY)


def _log_sigmoid(z: np.ndarray) -> np.ndarray:
    return -np.logaddexp(0.0, -z)


def _sigmoid(z):
    return 0.5 * (1 + np.tanh(0.5 * np.asarray(z, dtype=float)))


def _objective(x: np.ndarray, d: _Data, prior: float, with_prior: bool = True) -> tuple[float, np.ndarray]:
    """Log posterior (or likelihood) and its gradient at ``x = (θ_1..6, δ, logit ε)``."""
    theta, delta, eta = x[:N_SKILLS], x[N_SKILLS], x[N_SKILLS + 1]
    eps = float(_sigmoid(eta))
    shift = delta * d.late[:, None] * K.SESSION_SHIFT[None, :]
    z = d.c[:, None] + d.a * (theta[None, :] - shift - d.b)
    q = np.where(d.mask, _sigmoid(-z), 0.0)
    log_eps, log_1m_eps = float(_log_sigmoid(np.array(eta))), float(_log_sigmoid(np.array(-eta)))
    log_p = d.mix * log_1m_eps + np.where(d.mask, _log_sigmoid(z), 0.0).sum(axis=1)
    log_p = np.minimum(log_p, -1e-12)
    log_miss = np.log(-np.expm1(log_p))  # ln(1 − p)
    p = np.exp(log_p)
    F = d.f.sum(axis=1)
    m = eps * K.E0[None, :] + q @ K.E  # G × 3 (only head groups use it)
    m = np.maximum(m, 1e-300)
    s = np.maximum(eps + q.sum(axis=1), 1e-300)
    mix_terms = (d.f * (np.log(m) - np.log(s)[:, None])).sum(axis=1)
    ll = float(((d.n - F) * log_p + F * log_miss + d.mix * mix_terms).sum())

    ratio = p / -np.expm1(log_p)  # p / (1 − p)
    coef = (d.n - F) - F * ratio  # on d ln p
    dq = q * (1 - q)
    per_class = (d.f / m) @ K.E.T  # G × 6: Σ_c f_c E_kc / m_c
    dz = coef[:, None] * q + d.mix[:, None] * dq * (F / s)[:, None] - d.mix[:, None] * dq * per_class
    dz = np.where(d.mask, dz, 0.0)
    g_theta = (dz * d.a).sum(axis=0)
    g_delta = float(-(dz * d.a * K.SESSION_SHIFT[None, :] * d.late[:, None]).sum())
    g_eta = float((coef * -eps * d.mix).sum() + (d.mix * eps * (1 - eps) * ((d.f / m) @ K.E0 - F / s)).sum())
    if not with_prior:
        return ll, np.concatenate([g_theta, [g_delta, g_eta]])

    # priors
    ll += float(-((theta - prior) ** 2).sum() / (2 * K.TAU**2) - delta**2 / (2 * K.DELTA_SD**2))
    ll += (K.ALPHA - 1) * log_eps + (K.BETA - 1) * log_1m_eps
    g_theta = g_theta - (theta - prior) / K.TAU**2
    g_delta -= delta / K.DELTA_SD**2
    g_eta += (K.ALPHA - 1) * (1 - eps) - (K.BETA - 1) * eps
    return ll, np.concatenate([g_theta, [g_delta, g_eta]])


def _solve(d: _Data, prior: float, x0: np.ndarray, max_iter: int = 200) -> tuple[np.ndarray, float, bool, str]:
    """Damped quasi-Newton: only uphill steps; reports failure instead of a number."""
    x = np.asarray(x0, dtype=float).copy()
    ll, g = _objective(x, d, prior)
    h = -_hessian(d, prior, x)  # the curvature of −ℓ: positive definite near a maximum
    lam, fresh = 1e-3, True
    for _ in range(max_iter):
        if np.abs(g).max() < 1e-5:
            return x, ll, bool(np.abs(x[:N_SKILLS] - prior).max() < GUARD), "converged"
        scale = np.maximum(np.abs(np.diag(h)), 1e-6)
        stepped = False
        for _ in range(40):
            try:
                step = np.linalg.solve(h + lam * np.diag(scale), g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            if not np.isfinite(step).all():
                lam *= 10
                continue
            ll_new, g_new = _objective(x + step, d, prior)
            if np.isfinite(ll_new) and ll_new >= ll:
                stepped = True
                break
            lam *= 10
        if not stepped:
            if fresh:
                return x, ll, False, "no step raises the fit"
            h, lam, fresh = -_hessian(d, prior, x), 1e-3, True  # the updated curvature misled: start it again
            continue
        y = g - g_new  # BFGS on −ℓ: the change of its gradient along the step
        sy = float(step @ y)
        if sy > 1e-12:
            hs = h @ step
            h = h + np.outer(y, y) / sy - np.outer(hs, hs) / float(step @ hs)
        x, ll, g, fresh = x + step, ll_new, g_new, False
        lam = max(lam / 5, 1e-9)
        if np.abs(step).max() < 1e-10:
            break
    flat = np.abs(g).max() < 1e-3
    return x, ll, bool(flat and np.abs(x[:N_SKILLS] - prior).max() < GUARD), "converged" if flat else "too many steps"


def _hessian(d: _Data, prior: float, x: np.ndarray, h: float = 1e-4) -> np.ndarray:
    """Hessian by central differences of the exact gradient."""
    k = len(x)
    out = np.zeros((k, k))
    for i in range(k):
        e = np.zeros(k)
        e[i] = h
        out[:, i] = (_objective(x + e, d, prior)[1] - _objective(x - e, d, prior)[1]) / (2 * h)
    return (out + out.T) / 2


# ------------------------------------------------------------------ accuracy (its own 1-D fit)
def _acc_score(theta: float, b: np.ndarray, n: np.ndarray, f: np.ndarray, prior: float) -> float:
    q = _sigmoid(-(K.C_ACC + K.A_ACC * (theta - b)))
    return float(K.A_ACC * ((n - f) * q - f * (1 - q)).sum() - (theta - prior) / K.TAU**2)


def fit_accuracy(groups: IrtGroups, prior: float) -> tuple[float, float, bool]:
    """θ_acc by bisection on its (monotone) score, its SE, and whether a root was found."""
    acc = groups.take(groups.kind == K.ACCURACY)
    b, n, f = acc.b_acc, acc.n, acc.f_a
    lo, hi = prior - 1.0, prior + 1.0
    while _acc_score(lo, b, n, f, prior) < 0 and prior - lo < GUARD:
        lo -= prior - lo
    while _acc_score(hi, b, n, f, prior) > 0 and hi - prior < GUARD:
        hi += hi - prior
    if _acc_score(lo, b, n, f, prior) < 0 or _acc_score(hi, b, n, f, prior) > 0:
        return math.nan, math.nan, False
    for _ in range(80):
        mid = (lo + hi) / 2
        if _acc_score(mid, b, n, f, prior) > 0:
            lo = mid
        else:
            hi = mid
    theta = (lo + hi) / 2
    q = _sigmoid(-(K.C_ACC + K.A_ACC * (theta - b)))
    info = 1 / K.TAU**2 + float((K.A_ACC**2 * n * q * (1 - q)).sum())
    return theta, math.sqrt(K.D / info), True


# ------------------------------------------------------------------ the whole fit
def _tested(groups: IrtGroups, theta: dict[str, float]) -> dict[str, tuple[float, float]]:
    """Per skill: items, and the information-weighted 95th percentile of the held notes' difficulty."""
    groups = groups.take(groups.kind != K.TIMING)
    held = groups.n - groups.failed()
    b = np.column_stack([groups.b(), groups.b_acc]) if len(groups) else np.zeros((0, 7))
    out = {}
    for i, k in enumerate((*K.SKILLS, "acc")):
        col = b[:, i]
        ok = np.isfinite(col)
        items = float(groups.n[ok].sum())
        a, c = (K.A_ACC, K.C_ACC) if k == "acc" else (K.A[i], K.C)
        q = _sigmoid(-(c + a * (theta.get(k, 0.0) - col[ok])))
        w = held[ok] * a * a * q * (1 - q)
        out[k] = (items, weighted_quantile(col[ok], w, 0.95) if ok.any() and w.sum() > 0 else math.nan)
    return out


def held_bound(groups: IrtGroups, skill: str) -> float:
    """The hardest 0.5★ band of the skill's notes held at its anchor share or better; NaN if none."""
    groups = groups.take(groups.kind != K.TIMING)
    if skill == "acc":
        b, share = groups.b_acc, 1 - K.PI_ACC
    else:
        b, share = getattr(groups, f"b_{skill}"), 1 - K.PI
    ok = np.isfinite(b)
    if not ok.any():
        return math.nan
    band = np.floor(b[ok] / BAND) * BAND
    n, failed = groups.n[ok], groups.failed()[ok]
    best = math.nan
    for lo in np.unique(band):
        m = band == lo
        total = float(n[m].sum())
        if total >= BAND_ITEMS and float(failed[m].sum()) <= share * total:
            best = float(lo + BAND / 2) if math.isnan(best) else max(best, float(lo + BAND / 2))
    return best


def _typical(groups: IrtGroups, prior: float) -> np.ndarray:
    """A start for every skill: the median difficulty of its notes."""
    groups = groups.take(groups.kind != K.TIMING)
    b = groups.b() if len(groups) else np.zeros((0, N_SKILLS))
    out = np.full(N_SKILLS, prior)
    for i in range(N_SKILLS):
        ok = np.isfinite(b[:, i])
        if ok.any() and groups.n[ok].sum() > 0:
            out[i] = weighted_quantile(b[ok, i], groups.n[ok], 0.5)
    return out


def _cluster_var(x: np.ndarray, prior: float, hess: np.ndarray, parts: Sequence[IrtGroups]) -> np.ndarray:
    """Sandwich variance with every play as one cluster."""
    inv = np.linalg.inv(-hess)
    meat = np.zeros_like(hess)
    for part in parts:
        if len(part):
            g = _objective(x, _data(part), prior, with_prior=False)[1]
            meat += np.outer(g, g)
    return inv @ meat @ inv


def _acc_cluster_var(theta: float, parts: Sequence[IrtGroups]) -> float:
    """The same for accuracy."""
    scores, info = [], 1 / K.TAU**2
    for part in parts:
        acc = part.take(part.kind == K.ACCURACY)
        if not len(acc):
            continue
        q = _sigmoid(-(K.C_ACC + K.A_ACC * (theta - acc.b_acc)))
        scores.append(float(K.A_ACC * ((acc.n - acc.f_a) * q - acc.f_a * (1 - q)).sum()))
        info += float((K.A_ACC**2 * acc.n * q * (1 - q)).sum())
    return float(np.sum(np.square(scores))) / info**2


def fit(
    groups: IrtGroups,
    prior: float,
    plays: dict[str, float] | None = None,
    parts: Sequence[IrtGroups] | None = None,
) -> IrtFit:
    """The fit of these merged groups; with ``parts`` (each play's groups) the ranges are clustered by play."""
    plays = plays or {}
    d = _data(groups)
    x_init = np.concatenate([np.full(N_SKILLS, prior), [0.0, math.log(K.EPS0 / (1 - K.EPS0))]])
    starts = []
    for offset in STARTS:  # every skill at the prior centre, two stars below it and two above ...
        x0 = x_init.copy()
        x0[:N_SKILLS] += offset
        starts.append(x0)
    crude = x_init.copy()  # ... and each skill at its own typical difficulty
    crude[:N_SKILLS] = _typical(_data_groups(groups), prior)
    starts.append(crude)
    runs = [_solve(d, prior, x0) for x0 in starts]
    good = [r for r in runs if r[2]]
    acc_theta, acc_se, acc_ok = fit_accuracy(groups, prior)
    if not good:
        return IrtFit({}, math.nan, math.nan, math.nan, prior, False, message=runs[0][3])
    best = max(good, key=lambda r: r[1])
    x = best[0]
    hess = _hessian(d, prior, x)
    try:
        cov = np.linalg.inv(-hess)
        ok_cov = bool(np.all(np.isfinite(cov)) and np.all(np.diag(cov) > 0))
    except np.linalg.LinAlgError:
        ok_cov, cov = False, None
    if not ok_cov:
        return IrtFit({}, math.nan, math.nan, math.nan, prior, False, best[1], "the fit's curvature is not usable")

    # how far the answer follows the prior centre, and other answers that fit about as well
    shifts = []
    for move in (-SENSITIVITY, SENSITIVITY):
        x_moved, _, ok_moved, _ = _solve(d, prior + move, x)
        shifts.append(x_moved[:N_SKILLS] if ok_moved else x[:N_SKILLS])
    prior_shift = np.abs(shifts[1] - shifts[0]) / 2
    near = [r[0][:N_SKILLS] for r in good if best[1] - r[1] < K.MODE_LOGLIK]
    lo_modes, hi_modes = np.min(near, axis=0), np.max(near, axis=0)

    tested = _tested(groups, {**dict(zip(K.SKILLS, x[:N_SKILLS].tolist(), strict=True)), "acc": acc_theta})
    clustered = np.diag(_cluster_var(x, prior, hess, parts)) if parts else None
    skills: dict[str, SkillFit] = {}
    for i, k in enumerate(K.SKILLS):
        items, top = tested[k]
        n_plays = plays.get(k, 0.0)
        if clustered is not None:  # never narrower than the model's own curvature
            var = K.D_CLUSTER * max(float(clustered[i]), float(cov[i, i]))
        else:
            var = K.D * cov[i, i] + (K.FORM_SD**2 / max(n_plays, 1.0) if items else 0.0)
        se = math.sqrt(var + prior_shift[i] ** 2)
        spread = (float(lo_modes[i]), float(hi_modes[i])) if hi_modes[i] - lo_modes[i] > K.MODE_GAP else None
        skills[k] = SkillFit(float(x[i]), se, items, top, n_plays, spread, float(prior_shift[i]))
    items, top = tested["acc"]
    if acc_ok:
        acc_moved = [fit_accuracy(groups, prior + m)[0] for m in (-SENSITIVITY, SENSITIVITY)]
        acc_shift = abs(acc_moved[1] - acc_moved[0]) / 2 if all(map(math.isfinite, acc_moved)) else 0.0
        if parts:
            var = K.D_CLUSTER * max(_acc_cluster_var(acc_theta, parts), acc_se**2 / K.D)
        else:
            var = acc_se**2 + (K.FORM_SD**2 / max(plays.get("acc", 0.0), 1.0) if items else 0.0)
        skills["acc"] = SkillFit(
            acc_theta, math.sqrt(var + acc_shift**2), items, top, plays.get("acc", 0.0), None, acc_shift
        )
    eps = float(_sigmoid(x[N_SKILLS + 1]))
    return IrtFit(
        skills=skills,
        delta=float(x[N_SKILLS]),
        delta_se=math.sqrt(
            K.D_CLUSTER * max(float(clustered[N_SKILLS]), float(cov[N_SKILLS, N_SKILLS]))
            if clustered is not None
            else K.D * cov[N_SKILLS, N_SKILLS]
        ),
        eps=eps,
        prior=prior,
        converged=True,
        loglik=best[1],
        message=best[3],
        cov=K.D * cov[:N_SKILLS, :N_SKILLS],
    )

"""Map suggestions and skill playlists from the bundled map pool."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING

import pandas as pd

from osu_coach.app.convert import integer, num, text
from osu_coach.app.errors import ApiError, Invalid
from osu_coach.maps.domain import SKILLS, Targets, collection_name, skill_label, targets_from_profile
from osu_coach.maps.schemas import MapRow, Playlist, PlaylistSkill, PlaylistStage, Suggestions, SuggestionSection
from osu_coach.maps.skillset import recommend
from osu_coach.profile.domain import Profile

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace


def map_rows(df: pd.DataFrame | None) -> list[MapRow]:
    if df is None or df.empty:
        return []
    return [
        MapRow(
            md5=str(r["md5"]),
            beatmap_id=integer(r.get("beatmap_id")) or 0,
            beatmapset_id=integer(r.get("beatmapset_id")) or 0,
            artist=text(r.get("artist")) or "",
            title=text(r.get("title")) or "",
            version=text(r.get("version")) or "",
            creator=text(r.get("creator")),
            stars=num(r.get("stars")),
            bpm=num(r.get("bpm")),
            ar=num(r.get("ar")),
            od=num(r.get("od")),
            length_s=num(r.get("drain_length")),
            why=text(r.get("why")) or "",
            url=text(r.get("url")) or "",
            stage=text(r.get("stage")),
            goal=text(r.get("goal")),
            skill_demand=num(r.get("skill_demand")),
            relevance=num(r.get("relevance")),
            formula_score=num(r.get("formula_score")),
            breakdown=r.get("breakdown") if isinstance(r.get("breakdown"), dict) else None,
        )
        for r in df.to_dict("records")
    ]


def _pool(ws: Workspace) -> pd.DataFrame:
    pool = ws.pool()
    if pool.empty:
        raise ApiError(500, "pool_missing", "The bundled map pool is missing.")
    return pool


def default_skill(p: Profile | None, abilities: dict[str, float]) -> str:
    """The skill a playlist opens on: the first weakness with a rating (a skill without one has no maps to offer,
    e.g. consistency before 8 maps around the comfort level are played), else aim."""
    return next((k for k in (p.weaknesses if p else []) if k in SKILLS and k in abilities), "aim")


def _options(
    p: Profile | None,
    skill: str | None,
    assessed: str | None,
    ratings: str | None,
    comfort: float | None,
    kappa: float,
    min_relevance: float,
):
    if comfort is not None and num(comfort) is None:
        raise Invalid("Comfort stars must be a finite positive number.", "invalid_recommendation_settings")
    theta = num(comfort) if comfort is not None else None
    source = "Manual" if theta is not None else "Replay comfort"
    if theta is None and p:
        theta = num(p.levels.get("comfort_stars"))
    if theta is None and p:
        theta = num(p.levels.get("level_stars"))
        source = "Recent replay level fallback"
    if theta is None:
        theta = 2.5  # Visible starting assumption until the user supplies comfort stars.
        source = "Unmeasured 2.5★ starting assumption"
    measured = {key: row.get("score") for key, row in p.experimental_skills.items()} if p else {}
    abilities = {k: float(v) for k, v in measured.items() if k in SKILLS and v is not None}
    if ratings:
        try:
            manual = json.loads(ratings)
        except json.JSONDecodeError as exc:
            raise Invalid("Manual ratings must be a JSON object.", "invalid_ratings") from exc
        if not isinstance(manual, dict):
            raise Invalid("Manual ratings must be a JSON object.", "invalid_ratings")
        for key, value in manual.items():
            if (
                key not in SKILLS
                or isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 100
            ):
                raise Invalid(f"Invalid 0–100 rating for {key}.", "invalid_ratings")
            abilities[key] = float(value)
    target = skill or default_skill(p, abilities)
    if target not in SKILLS:
        raise Invalid(f"Unknown skill {target}.", "unknown_skill")
    checked = tuple(dict.fromkeys(assessed.split(",") if assessed is not None else [target]))
    if not checked or target not in checked or set(checked) - set(SKILLS):
        raise Invalid("Assessed skills must include the target skill.", "invalid_assessed_skills")
    if (
        theta <= 0
        or not math.isfinite(kappa)
        or kappa < 0
        or not math.isfinite(min_relevance)
        or not 0 <= min_relevance <= 1
    ):
        raise Invalid("Invalid recommendation settings.", "invalid_recommendation_settings")
    return target, checked, abilities, theta, source


def suggestions(
    ws: Workspace,
    p: Profile | None,
    kappa: float = 0.5,
    min_relevance: float = 0.3,
) -> Suggestions:
    pool = _pool(ws)
    _, _, abilities, theta, source = _options(p, None, None, None, None, kappa, min_relevance)
    # Use the same measured <=45 scores and three-skill limit as Overview.
    weak = sorted(
        (key for key in SKILLS if abilities.get(key, 101) <= 45), key=lambda key: (abilities[key], SKILLS.index(key))
    )[:3]
    t = targets_from_profile(p) if p else Targets(comfort=theta)
    t.comfort = theta
    hidden = set(ws.settings().get("hidden_maps") or [])
    if hidden:
        pool = pool[~pool["md5"].isin(hidden)]
    sections = []
    for target in weak:
        try:
            ranked = recommend(pool, theta, abilities, target, tuple(weak), kappa, min_relevance, t.played, t)
        except ValueError as exc:
            raise Invalid(str(exc), "invalid_recommendation_settings") from exc
        data = ranked["goals"]["Comfort"]
        label = skill_label(target)
        sections.append(
            SuggestionSection(
                skill=target,
                title=label,
                score=abilities[target],
                skill_adjusted_stars=ranked["skill_adjusted_stars"],
                target_stars=data["target_stars"],
                target_demand=data["target_demand"],
                eligible=data["eligible"],
                excluded=data["excluded"],
                maps=map_rows(pd.DataFrame(data["maps"]).assign(stage=label, goal="Comfort")),
            )
        )
    return Suggestions(
        comfort=theta,
        comfort_source=source,
        pool_size=len(ws.pool()),
        hidden=len(hidden),
        sections=sections,
        collection_name=f"osu-coach: Map Suggestion ({theta:.1f}★)",
        preferred_client=ws.preferred_client(),
        has_profile=p is not None,
        unmeasured_skills=[skill_label(key) for key in SKILLS if key not in abilities],
    )


def hide(ws: Workspace, md5s: list[str]) -> int:
    hidden = set(ws.settings().get("hidden_maps") or []) | set(md5s)
    ws.update_settings(hidden_maps=sorted(hidden))
    return len(hidden)


def playlist(
    ws: Workspace,
    skill: str | None,
    comfort: float | None,
    assessed: str | None = None,
    ratings: str | None = None,
    kappa: float = 0.5,
    min_relevance: float = 0.3,
    exclude_played: bool = True,
) -> Playlist:
    pool = _pool(ws)
    p = ws.profile()
    target, checked, abilities, theta, source = _options(p, skill, assessed, ratings, comfort, kappa, min_relevance)
    t = targets_from_profile(p) if p else Targets(comfort=theta)
    t.comfort = theta
    default = default_skill(p, abilities)
    try:
        ranked = recommend(
            pool,
            theta,
            abilities,
            target,
            checked,
            kappa,
            min_relevance,
            t.played if exclude_played else frozenset(),
            t,
        )
    except ValueError as exc:
        raise Invalid(str(exc), "invalid_recommendation_settings") from exc
    stages = [
        PlaylistStage(
            stage=stage,
            goal=stage,
            target_stars=data["target_stars"],
            target_demand=data["target_demand"],
            eligible=data["eligible"],
            excluded=data["excluded"],
            maps=map_rows(pd.DataFrame(data["maps"]).assign(stage=stage, goal=stage)),
        )
        for stage, data in ranked["goals"].items()
    ]
    skills = [PlaylistSkill(key=k, label=skill_label(k, t), score=abilities.get(k)) for k in SKILLS]
    return Playlist(
        skill=target,
        skills=skills,
        default_skill=default,
        has_profile=p is not None,
        comfort=theta,
        comfort_source=source,
        stream_bpm=num(t.stream_bpm),
        maps=sum(stage.eligible for stage in stages),
        collection_name=collection_name(target, t),
        stages=stages,
        preferred_client=ws.preferred_client(),
        skill_adjusted_stars=ranked["skill_adjusted_stars"],
        abilities=abilities,
        measured_abilities={
            key: float(row["score"])
            for key, row in (p.experimental_skills.items() if p else [])
            if key in SKILLS and row.get("score") is not None
        },
    )

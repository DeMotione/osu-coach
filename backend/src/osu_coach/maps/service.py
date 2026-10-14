"""Map suggestions and skill playlists from the bundled map pool."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from osu_coach.app.convert import integer, num, text
from osu_coach.app.errors import ApiError, Invalid
from osu_coach.maps.domain import (
    PLAYLIST_SKILLS,
    SKILLS,
    Targets,
    build_playlist,
    collection_name,
    recommendations,
    skill_label,
    targets_from_profile,
)
from osu_coach.maps.schemas import MapRow, Playlist, PlaylistSkill, PlaylistStage, Suggestions, SuggestionSection
from osu_coach.profile.domain import Profile

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace


SUGGESTIONS_PER_SKILL = 5


def map_rows(df: pd.DataFrame | None) -> list[MapRow]:
    if df is None or df.empty:
        return []
    rows = []
    for r in df.to_dict("records"):
        rows.append(
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
            )
        )
    return rows


def _pool(ws: Workspace) -> pd.DataFrame:
    pool = ws.pool()
    if pool.empty:
        raise ApiError(500, "pool_missing", "The bundled map pool is missing.")
    return pool


# ------------------------------------------------------------------ suggestions
def suggestions(ws: Workspace, p: Profile) -> Suggestions:
    pool = _pool(ws)
    t = targets_from_profile(p)
    hidden = set(ws.settings().get("hidden_maps") or [])
    if hidden:
        pool = pool[~pool["md5"].isin(hidden)]
    sections = []
    for sk, df in recommendations(pool, p, per_skill=SUGGESTIONS_PER_SKILL):
        title = "Level up" if sk == "general" else skill_label(sk, t)
        score = None if sk in ("general", "quadrant") else num(p.skills.get(sk, {}).get("score"))
        sections.append(
            SuggestionSection(skill=sk, title=title, score=score, maps=map_rows(df.assign(stage=skill_label(sk, t))))
        )
    return Suggestions(
        comfort=float(t.comfort),
        pool_size=len(ws.pool()),
        hidden=len(hidden),
        sections=sections,
        collection_name=f"osu-coach: Map Suggestion ({t.comfort:.1f}★)",
        preferred_client=ws.preferred_client(),
    )


def hide(ws: Workspace, md5s: list[str]) -> int:
    hidden = set(ws.settings().get("hidden_maps") or []) | set(md5s)
    ws.update_settings(hidden_maps=sorted(hidden))
    return len(hidden)


# ------------------------------------------------------------------ playlists
def playlist(ws: Workspace, skill: str | None, n: int, comfort: float | None) -> Playlist:
    pool = _pool(ws)
    p = ws.profile()
    if p is not None:
        t = targets_from_profile(p)
    else:
        t = Targets(comfort=float(comfort if comfort is not None else ws.settings().get("manual_comfort", 2.5)))
    options = SKILLS + (["quadrant"] if t.quadrant else [])
    default = p.weaknesses[0] if p is not None and p.weaknesses else "aim"
    default = default if default in options else options[0]
    skill = skill or default
    if skill not in PLAYLIST_SKILLS:
        raise Invalid(f"Unknown skill {skill}.", "unknown_skill")
    if skill == "quadrant" and not t.quadrant:
        raise ApiError(409, "no_weak_quadrant", "No clearly weak quadrant in your replays — pick another skill.")
    pl = build_playlist(pool, skill, t, n=n)
    stages = (
        [
            PlaylistStage(stage=str(stage), goal=str(part["goal"].iloc[0]), maps=map_rows(part))
            for stage, part in pl.groupby("stage", sort=False)
        ]
        if not pl.empty
        else []
    )
    skills = [
        PlaylistSkill(
            key=k, label=skill_label(k, t), score=num(p.skills.get(k, {}).get("score")) if p is not None else None
        )
        for k in options
    ]
    return Playlist(
        skill=skill,
        skills=skills,
        default_skill=default,
        has_profile=p is not None,
        comfort=float(t.comfort),
        stream_bpm=num(t.stream_bpm),
        maps=n,
        collection_name=collection_name(skill, t),
        stages=stages,
        preferred_client=ws.preferred_client(),
    )

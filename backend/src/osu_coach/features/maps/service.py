"""Map suggestions and skill playlists from the bundled map pool."""

from __future__ import annotations

import concurrent.futures as cf
import json
import math
import multiprocessing
import os
from collections import deque
from dataclasses import replace
from typing import TYPE_CHECKING

import pandas as pd

from osu_coach.common.convert import integer, iso, num, text
from osu_coach.common.errors import ApiError, Invalid
from osu_coach.common.maps import map_rows
from osu_coach.common.texts import explain
from osu_coach.domain.maps.configuration import SearchOptions
from osu_coach.domain.maps.skillset import recommend, recommend_modified, star_targets
from osu_coach.domain.maps.suggestions import (
    SKILLS,
    Targets,
    collection_name,
    map_url,
    skill_label,
    targets_from_profile,
)
from osu_coach.domain.player import Profile
from osu_coach.domain.player.engines import make_engine
from osu_coach.domain.replays.configuration import from_meta
from osu_coach.features.maps.schemas import (
    CompletedMap,
    Playlist,
    PlaylistSearchRequest,
    PlaylistSkill,
    PlaylistStage,
    Suggestions,
    SuggestionSection,
)
from osu_coach.features.maps.variant_repository import calculate_variants, verified_bytes

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace


def _scanned(ws: Workspace) -> list[dict]:
    """The player's osu!standard replays the scan found (osu! saves a replay only for a finished play)."""
    player = ws.settings().player
    replays = ws.library.replays if ws.library is not None else []
    return [
        r
        for r in replays
        if r.get("mode") == 0 and r.get("beatmap_md5") and (not player or player == "*" or r.get("player") == player)
    ]


def _played(ws: Workspace, t: Targets) -> frozenset[str]:
    """Maps the player already finished: those of the analysed replays plus those of every osu!standard replay of the
    player the scan found, so a map completed outside the analysed set (only the latest N analysed, or picked files)
    isn't suggested again (#47)."""
    return t.played | frozenset(str(r["beatmap_md5"]) for r in _scanned(ws))


def completed(ws: Workspace) -> list[CompletedMap]:
    """The pool maps the player has finished (what playlists leave out as already played), last finished first."""
    pool = _pool(ws)
    p = ws.profile()
    last: dict[str, str | None] = {}

    def seen(md5: str, when) -> None:
        at = iso(when)
        if md5 not in last or (at or "") > (last[md5] or ""):
            last[md5] = at

    for m in p.replays if p else ():
        if m.beatmap_md5:
            seen(str(m.beatmap_md5), m.date)
    for r in _scanned(ws):
        seen(str(r["beatmap_md5"]), r.get("timestamp"))
    rows = pool[pool["md5"].isin(last.keys())].to_dict("records")
    maps = [
        CompletedMap(
            md5=str(r["md5"]),
            beatmap_id=max(0, integer(r.get("beatmap_id")) or 0),
            beatmapset_id=max(0, integer(r.get("beatmapset_id")) or 0),
            artist=text(r.get("artist")) or "",
            title=text(r.get("title")) or "",
            version=text(r.get("version")) or "",
            stars=num(r.get("stars")),
            url=map_url(r),
            played_at=last[str(r["md5"])],
        )
        for r in rows
    ]
    return sorted(maps, key=lambda m: (m.played_at or "", m.md5), reverse=True)


def _pool(ws: Workspace) -> pd.DataFrame:
    pool = ws.pool()
    if pool.empty:
        raise ApiError(503, "pool_missing", "The bundled map pool is missing.")
    return pool


def default_skill(p: Profile | None, abilities: dict[str, float]) -> str:
    """The skill a playlist opens on: the first weakness with a rating (a skill without one has no maps to offer,
    e.g. consistency before 8 maps around the comfort level are played), else aim."""
    return next((k for k in (p.weaknesses if p else []) if k in SKILLS and k in abilities), "aim")


def _comfort_of(p: Profile | None) -> float:
    """The level suggestions are made for: the comfort level, else the replay level."""
    return (num(p.levels.comfort_stars) or num(p.levels.level_stars) or 2.5) if p else 2.5


def measured_abilities(p: Profile | None, theta: float) -> dict[str, float]:
    """The scores suggestions work from: measurements only, on the scale the recommender reads."""
    if p is None:
        return {}
    scores = make_engine(p.engine).map_scores(p.skill_ratings, theta)
    return {k: v for k, v in scores.items() if k in SKILLS}


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
        theta = num(p.levels.comfort_stars)
    if theta is None and p:
        theta = num(p.levels.level_stars)
        source = "Recent replay level fallback"
    if theta is None:
        theta = 2.5  # Visible starting assumption until the user supplies comfort stars.
        source = "Unmeasured 2.5★ starting assumption"
    measured = measured_abilities(p, theta)
    abilities = dict(measured)
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
    t.played = _played(ws, t)
    hidden = set(ws.settings().hidden_maps or [])
    if hidden:
        pool = pool[~pool["md5"].isin(hidden)]
    sections = []
    for target in weak:
        try:
            ranked = explain(
                recommend(
                    pool.to_dict("records"), theta, abilities, target, tuple(weak), kappa, min_relevance, t.played
                ),
                target,
                t,
            )
        except ValueError as exc:
            raise Invalid(str(exc), "invalid_recommendation_settings") from exc
        data = ranked.goals["Comfort"]
        label = skill_label(target)
        sections.append(
            SuggestionSection(
                skill=target,
                title=label,
                score=abilities[target],
                skill_adjusted_stars=ranked.skill_adjusted_stars,
                target_stars=data.target_stars,
                target_demand=data.target_demand,
                eligible=data.eligible,
                excluded=data.excluded,
                maps=map_rows(data.maps, stage=label, goal="Comfort"),
            )
        )
    return Suggestions(
        comfort=theta,
        comfort_source=source,
        pool_size=len(ws.pool()),
        hidden=len(hidden),
        sections=sections,
        collection_name=f"osu-coach: Skill Development ({theta:.1f}★)",
        preferred_client=ws.preferred_client(),
        has_profile=p is not None,
        unmeasured_skills=[skill_label(key) for key in SKILLS if key not in abilities],
    )


def hide(ws: Workspace, md5s: list[str]) -> int:
    hidden = set(ws.settings().hidden_maps or []) | set(md5s)
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
    t.played = _played(ws, t)
    default = default_skill(p, abilities)
    try:
        ranked = recommend(
            pool.to_dict("records"),
            theta,
            abilities,
            target,
            checked,
            kappa,
            min_relevance,
            t.played if exclude_played else frozenset(),
        )
        ranked = explain(ranked, target, t)
    except ValueError as exc:
        raise Invalid(str(exc), "invalid_recommendation_settings") from exc
    stages = [
        PlaylistStage(
            stage=stage,
            goal=stage,
            target_stars=data.target_stars,
            target_demand=data.target_demand,
            eligible=data.eligible,
            excluded=data.excluded,
            maps=map_rows(data.maps, stage=stage, goal=stage),
        )
        for stage, data in ranked.goals.items()
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
        skill_adjusted_stars=ranked.skill_adjusted_stars,
        abilities=abilities,
        measured_abilities=measured_abilities(p, _comfort_of(p)),
    )


def validate_search(ws: Workspace, req: PlaylistSearchRequest) -> None:
    SearchOptions(req.allow_hr, req.allow_hd, req.adjustable_dt, req.min_rate, req.max_rate)
    _options(ws.profile(), req.skill, req.assessed, req.ratings, req.comfort, req.kappa, req.min_relevance)


def with_pool_ids(row: dict, record) -> dict:
    """A calculated variant with the pool's beatmap and set ids. Variants are calculated from the .osu file, and
    old .osu files don't name their beatmap or set (they read as 0); the pool, from the osu! website, does."""
    ids = {k: v for k in ("beatmap_id", "beatmapset_id") if (v := integer(record.get(k))) is not None and v > 0}
    return {**row, **ids} if ids else row


def _calculate_map(cache_dir, raw, options, md5, client, *screen):
    """One map's configurations, made where they are calculated: hundreds a map, slow to send to a worker."""
    return calculate_variants(cache_dir, raw, options.configurations(md5, client), *screen)


def _search_map_results(cache_dir, records, libraries, options, client, report, workers=None, targets=None):
    """Yield map results in pool order while calculating different maps in parallel.

    Retrieval stays on this thread: the download helper shares an HTTP session. At
    most one process owns a map's fixed cache temp path at a time. A cancelled job
    waits for active map calculations to finish before its exclusive gate opens.
    ``targets`` (the goals' target stars): rows only for the configurations a goal
    can rank, the rest of a map's counted (see ``variant_rows``).
    """
    total = len(records)
    screen = () if targets is None else (targets,)
    workers = workers if workers is not None else max(1, min(8, (os.cpu_count() or 2) - 1))
    n_configs = len(options.configurations("", client))  # the same for every map

    def prepare(index):
        row = records[index]
        return index, str(row["md5"]), verified_bytes(cache_dir, row, libraries)

    def calculate(item):
        index, md5, raw = item
        if raw is None:
            return index, False, [], 0, 0
        try:
            rows, unavailable = _calculate_map(cache_dir, raw, options, md5, client, *screen)
        except (OSError, ValueError):
            rows, unavailable = [], n_configs
        return index, True, rows, unavailable, n_configs

    if workers == 1:
        for index in range(total):
            report(index, total, f"Checking map {index + 1} of {total}")
            yield calculate(prepare(index))
        report(total, total, "Ranking complete")
        return

    try:
        pool = cf.ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"))
    except (OSError, RuntimeError):
        for index in range(total):
            report(index, total, f"Checking map {index + 1} of {total}")
            yield calculate(prepare(index))
        report(total, total, "Ranking complete")
        return

    pending = deque()
    active_md5 = set()
    next_index = 0
    completed = 0
    broken = False
    try:
        while next_index < total or pending:
            report(completed, total, f"Checking map {completed + 1} of {total}")
            while next_index < total and len(pending) < 2 * workers:
                md5 = str(records[next_index]["md5"])
                if md5 in active_md5:
                    break
                report(completed, total, f"Checking map {next_index + 1} of {total}")
                item = prepare(next_index)
                future = None
                if item[2] is not None:
                    try:
                        future = pool.submit(_calculate_map, cache_dir, item[2], options, md5, client, *screen)
                    except (OSError, RuntimeError, cf.process.BrokenProcessPool):
                        broken = True
                pending.append((item, future))
                if future is not None:
                    active_md5.add(md5)
                next_index += 1
                if broken:
                    break
            if broken:
                break
            item, future = pending[0]
            if future is None:
                result = calculate(item)
            else:
                try:
                    rows, unavailable = future.result(timeout=0.25)
                except cf.TimeoutError:
                    continue
                except cf.process.BrokenProcessPool:
                    broken = True
                    break
                except (OSError, ValueError):
                    rows, unavailable = [], n_configs
                result = item[0], True, rows, unavailable, n_configs
            pending.popleft()
            active_md5.discard(item[1])
            completed += 1
            report(completed, total, f"Checking map {completed} of {total}")
            yield result
    finally:
        # In particular, do not release a cancelled job's gate while workers
        # can still write the same versioned cache files as the next search.
        pool.shutdown(wait=True, cancel_futures=True)

    if broken:
        # A worker may have finished a cache write before the pool broke. The
        # serial path reads that cache and only computes configurations missing
        # from it; no completed pool row is counted twice.
        for item, _ in pending:
            report(completed, total, f"Checking map {completed + 1} of {total}")
            yield calculate(item)
            completed += 1
        for index in range(next_index, total):
            report(completed, total, f"Checking map {completed + 1} of {total}")
            yield calculate(prepare(index))
            completed += 1
    report(total, total, "Ranking complete")


def search(ws: Workspace, req: PlaylistSearchRequest, report) -> Playlist:
    """Exact available-map search, run only inside a cancellable background job."""
    options = SearchOptions(req.allow_hr, req.allow_hd, req.adjustable_dt, req.min_rate, req.max_rate)
    pool = _pool(ws)
    p = ws.profile()
    target, checked, abilities, theta, source = _options(
        p, req.skill, req.assessed, req.ratings, req.comfort, req.kappa, req.min_relevance
    )
    t = targets_from_profile(p) if p else Targets(comfort=theta)
    t.comfort = theta
    t.played = _played(ws, t)
    client = ws.preferred_client()
    history = {}
    for analysis in ws.plays:
        meta = analysis.meta
        acc = num(meta.accuracy)
        if meta.completed and acc is not None:
            key = from_meta(meta.to_dict()).key
            history[key] = max(history.get(key, 0.0), min(1.10, max(0.0, acc / 0.95)))
    libraries = ws.libraries()
    unavailable = 0
    coverage = 0
    calculator_unavailable = 0
    unavailable_configurations = 0
    records = pool.to_dict("records")
    targets = star_targets(theta, req.kappa, abilities, target)

    def rows():
        nonlocal unavailable, coverage, calculator_unavailable, unavailable_configurations
        for index, found, calculated, failed_configs, _ in _search_map_results(
            ws.cache_dir, records, libraries, options, client, report, targets=targets
        ):
            if not found:
                unavailable += 1
                continue
            coverage += 1
            unavailable_configurations += failed_configs
            if not calculated:
                calculator_unavailable += 1
            yield from (with_pool_ids(row, records[index]) if isinstance(row, dict) else row for row in calculated)

    ranked = recommend_modified(
        records,
        rows(),
        theta,
        abilities,
        target,
        checked,
        req.kappa,
        req.min_relevance,
        t.played if req.exclude_played else frozenset(),
        history,
    )
    ranked = explain(ranked, target, t)
    if ranked.candidate_count == 0 and all(key in abilities for key in checked):
        none = {"No available exact configurations": 1}
        goals = {name: replace(data, excluded={**data.excluded, **none}) for name, data in ranked.goals.items()}
        ranked = replace(ranked, goals=goals)
    stages = [
        PlaylistStage(
            stage=stage,
            goal=stage,
            target_stars=data.target_stars,
            target_demand=data.target_demand,
            eligible=data.eligible,
            excluded=data.excluded,
            maps=map_rows(data.maps, stage=stage, goal=stage),
        )
        for stage, data in ranked.goals.items()
    ]
    return Playlist(
        skill=target,
        skills=[PlaylistSkill(key=k, label=skill_label(k, t), score=abilities.get(k)) for k in SKILLS],
        default_skill=default_skill(p, abilities),
        has_profile=p is not None,
        comfort=theta,
        comfort_source=source,
        stream_bpm=num(t.stream_bpm),
        maps=sum(stage.eligible for stage in stages),
        collection_name=collection_name(target, t),
        stages=stages,
        preferred_client=client,
        skill_adjusted_stars=ranked.skill_adjusted_stars,
        abilities=abilities,
        measured_abilities=measured_abilities(p, _comfort_of(p)),
        coverage_maps=coverage,
        unavailable_maps=unavailable,
        calculator_unavailable_maps=calculator_unavailable,
        unavailable_configurations=unavailable_configurations,
        result_limit=ranked.result_limit,
    )

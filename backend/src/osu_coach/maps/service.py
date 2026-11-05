"""Map suggestions and skill playlists from the bundled map pool."""

from __future__ import annotations

import concurrent.futures as cf
import json
import math
import multiprocessing
import os
from collections import deque
from typing import TYPE_CHECKING

import pandas as pd

from osu_coach.app.convert import integer, num, text
from osu_coach.app.errors import ApiError, Invalid
from osu_coach.maps.configuration import SearchOptions
from osu_coach.maps.domain import SKILLS, Targets, collection_name, skill_label, targets_from_profile
from osu_coach.maps.schemas import (
    MapRow,
    Playlist,
    PlaylistSearchRequest,
    PlaylistSkill,
    PlaylistStage,
    Suggestions,
    SuggestionSection,
)
from osu_coach.maps.skillset import recommend, recommend_modified
from osu_coach.maps.variant_repository import calculate_variants, verified_bytes
from osu_coach.profile.domain import Profile
from osu_coach.replays.configuration import from_meta

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
            configuration_id=text(r.get("configuration_id")),
            mods=text(r.get("mods")) or "NM",
            rate=num(r.get("rate")) or 1.0,
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


def _played(ws: Workspace, t: Targets) -> frozenset[str]:
    """Maps the player already finished: those of the analysed replays plus those of every osu!standard replay of the
    player the scan found (osu! saves a replay only for a finished play), so a map completed outside the analysed set
    (only the latest N analysed, or picked files) isn't suggested again (#47)."""
    player = ws.settings().get("player")
    replays = ws.library.replays if ws.library is not None else []
    scanned = {
        str(r["beatmap_md5"])
        for r in replays
        if r.get("mode") == 0 and r.get("beatmap_md5") and (not player or player == "*" or r.get("player") == player)
    }
    return t.played | frozenset(scanned)


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
    measured = {key: row.get("score") for key, row in p.skill_ratings.items()} if p else {}
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
    t.played = _played(ws, t)
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
        collection_name=f"osu-coach: Skill Development ({theta:.1f}★)",
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
    t.played = _played(ws, t)
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
            for key, row in (p.skill_ratings.items() if p else [])
            if key in SKILLS and row.get("score") is not None
        },
    )


def validate_search(ws: Workspace, req: PlaylistSearchRequest) -> None:
    SearchOptions(req.allow_hr, req.allow_hd, req.adjustable_dt, req.min_rate, req.max_rate)
    _options(ws.profile(), req.skill, req.assessed, req.ratings, req.comfort, req.kappa, req.min_relevance)


def _search_map_results(cache_dir, records, libraries, options, client, report, workers=None):
    """Yield map results in pool order while calculating different maps in parallel.

    Retrieval stays on this thread: the download helper shares an HTTP session. At
    most one process owns a map's fixed cache temp path at a time. A cancelled job
    waits for active map calculations to finish before its exclusive gate opens.
    """
    total = len(records)
    workers = workers if workers is not None else max(1, min(4, (os.cpu_count() or 2) - 1))

    def prepare(index):
        row = records[index]
        raw = verified_bytes(cache_dir, row, libraries)
        configs = options.configurations(str(row["md5"]), client) if raw is not None else ()
        return index, str(row["md5"]), raw, configs

    def calculate(item):
        index, _, raw, configs = item
        if raw is None:
            return index, False, [], 0, 0
        try:
            rows, unavailable = calculate_variants(cache_dir, raw, configs)
        except (OSError, ValueError):
            rows, unavailable = [], len(configs)
        return index, True, rows, unavailable, len(configs)

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
                        future = pool.submit(calculate_variants, cache_dir, item[2], item[3])
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
                    rows, unavailable = [], len(item[3])
                result = item[0], True, rows, unavailable, len(item[3])
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
    for analysis in ws.analyses:
        meta = analysis.meta
        acc = num(meta.get("accuracy"))
        if meta.get("completed") and acc is not None:
            key = from_meta(meta).key
            history[key] = max(history.get(key, 0.0), min(1.10, max(0.0, acc / 0.95)))
    libraries = [lib for lib in (ws.library, ws.check_library) if lib is not None]
    unavailable = 0
    coverage = 0
    calculator_unavailable = 0
    unavailable_configurations = 0
    records = pool.to_dict("records")

    def rows():
        nonlocal unavailable, coverage, calculator_unavailable, unavailable_configurations
        for _, found, calculated, failed_configs, _ in _search_map_results(
            ws.cache_dir, records, libraries, options, client, report
        ):
            if not found:
                unavailable += 1
                continue
            coverage += 1
            unavailable_configurations += failed_configs
            if not calculated:
                calculator_unavailable += 1
            yield from calculated

    ranked = recommend_modified(
        pool,
        rows(),
        theta,
        abilities,
        target,
        checked,
        req.kappa,
        req.min_relevance,
        t.played if req.exclude_played else frozenset(),
        t,
        history,
    )
    if ranked["candidate_count"] == 0 and all(key in abilities for key in checked):
        for data in ranked["goals"].values():
            data["excluded"]["No available exact configurations"] = 1
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
        skill_adjusted_stars=ranked["skill_adjusted_stars"],
        abilities=abilities,
        measured_abilities={
            key: float(row["score"])
            for key, row in (p.skill_ratings.items() if p else [])
            if key in SKILLS and row.get("score") is not None
        },
        coverage_maps=coverage,
        unavailable_maps=unavailable,
        calculator_unavailable_maps=calculator_unavailable,
        unavailable_configurations=unavailable_configurations,
        result_limit=ranked["result_limit"],
    )

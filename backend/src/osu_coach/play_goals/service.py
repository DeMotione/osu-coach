"""Composition of local player evidence, target analysis, and immediate next plays."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from osu_coach.app.errors import ApiError, Invalid
from osu_coach.check.service import check_library, require_replay_file
from osu_coach.jobs.manager import Reporter
from osu_coach.library.repository import Library
from osu_coach.maps.goal_repository import load_goal_pool
from osu_coach.play_goals import domain, repository
from osu_coach.play_goals.schemas import PlayGoalOptions, PlayGoalRequest, PlayGoalResult
from osu_coach.replays.eligibility import analysable
from osu_coach.replays.osr import lazer_info

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace


def selected_player(ws: Workspace) -> str | None:
    saved = ws.settings().get("player")
    players = {a.meta["player"] for a in ws.analyses}
    if saved and saved != "*":
        return saved
    return next(iter(players)) if len(players) == 1 else None


def revision(ws: Workspace) -> str:
    settings = ws.settings()
    value = (
        [a.key for a in ws.analyses],
        selected_player(ws),
        settings.get("replay_set"),
        settings.get("level_override"),
    )
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()[:16]


def pool_data() -> list[dict]:
    try:
        return load_goal_pool()
    except (ValueError, OSError) as exc:
        raise ApiError(503, "goal_pool_unavailable", str(exc)) from exc


def options(ws: Workspace) -> PlayGoalOptions:
    last = ws.settings().get("play_goal_request")
    try:
        remembered = PlayGoalRequest.model_validate(last) if last else None
    except ValidationError as exc:
        raise Invalid(
            "The saved Play Goals request is invalid. Submit a new goal to replace it.", "invalid_saved_goal"
        ) from exc
    pool = pool_data()
    return PlayGoalOptions(
        last_request=remembered,
        evidence_revision=revision(ws),
        player=selected_player(ws),
        players=sorted({a.meta["player"] for a in ws.analyses}),
        evidence_plays=len(ws.analyses),
        coverage_maps=len({r["md5"] for r in pool}),
    )


def validate_request(ws: Workspace, request: PlayGoalRequest) -> None:
    if request.goal == "fc":
        if request.replay_path:
            require_replay_file(ws, request.replay_path)
        else:
            try:
                domain.beatmap_id(request.beatmap or "")
            except ValueError as exc:
                raise Invalid(str(exc), "invalid_goal_beatmap") from exc


def verified_analyses(analyses: list) -> tuple[list, int]:
    unverified = 0
    for analysis in analyses:
        m = analysis.meta
        if m.get("client") == "lazer" and "goal_lazer_mods" not in m:
            path = m.get("source_path")
            if path and Path(path).is_file():
                info = lazer_info(Path(path).read_bytes())
                if info is not None:
                    m["goal_lazer_mods"] = info.get("mods")
            if "goal_lazer_mods" not in m:
                unverified += 1
    return analyses, unverified


def evaluate(ws: Workspace, request: PlayGoalRequest, report: Reporter) -> PlayGoalResult:
    report.note("Preparing map and mod evidence")
    ws.update_settings(play_goal_request=request.model_dump())
    pool = pool_data()
    player = selected_player(ws)
    evidence_revision = revision(ws)
    analyses = list(ws.analyses)
    target, replay_path = None, None
    client = request.client
    warnings = [
        f"Offline recommendations cover {len({r['md5'] for r in pool})} selected difficulties, not the entire osu! catalogue.",
        "PP values are conservative hit-result FC scenarios from the pinned calculator, not account PP gains. "
        "Accuracy rounding and slider outcomes can change PP.",
    ]
    if request.goal == "fc":
        if request.replay_path:
            path = require_replay_file(ws, request.replay_path)
            lib = check_library(ws)
            if lib is None:
                lib = ws.check_library = Library(ws.cache_dir)
            if not any(str(r["path"]) == str(path) for r in lib.replays):
                lib.add_files([path])
            ref = next((r for r in lib.replays if str(r["path"]) == str(path)), None)
            if ref is None or not analysable(ref):
                raise Invalid("This replay cannot be used for a standard play goal.", "goal_replay_unsupported")
            missing = lib.missing_maps([ref])
            if missing and request.online:
                lib.fetch_missing(missing)
            report.note("Analysing the target attempt")
            done, errors = lib.analyze([ref], workers=1)
            if not done:
                raise Invalid(
                    f"Could not analyse this replay: {errors[0][1] if errors else 'no result'}", "goal_analysis_failed"
                )
            selected = done[0]
            client = selected.meta["client"]
            replay_path = str(path)
            if player is None and not analyses:
                player = selected.meta["player"]
            if player != selected.meta["player"]:
                warnings.append(
                    "This replay belongs to another player. Its misses are not used to diagnose your blockers."
                )
            else:
                related = [
                    r
                    for r in lib.replays
                    if r.get("beatmap_md5") == ref["beatmap_md5"]
                    and r.get("player") == player
                    and str(r["path"]) != str(path)
                    and analysable(r)
                ][:30]
                report.note("Checking other attempts of this map")
                others, errors = lib.analyze(related, workers=1) if related else ([], [])
                if errors:
                    warnings.append(f"{len(errors)} other attempt(s) could not be analysed.")
                analyses.extend([selected, *others])
            map_path = lib.maps.get(ref["beatmap_md5"])
            if not map_path:
                raise Invalid("The target beatmap is missing.", "goal_map_unavailable")
            raw = Path(map_path).read_bytes()
        else:
            report.note("Resolving the target difficulty")
            client = "lazer"
            raw = repository.target_bytes(
                ws.cache_dir,
                domain.beatmap_id(request.beatmap or ""),
                [lib for lib in (ws.library, ws.check_library) if lib],
                request.online,
                pool,
            )
        report.note("Calculating the target configuration")
        try:
            target = repository.target_configuration(ws.cache_dir, raw, request.mods, client)
        except ValueError as exc:
            raise Invalid(str(exc), "goal_configuration_unsupported") from exc
        ranked = next((r for r in pool if r["md5"] == target["md5"]), None)
        if ranked:
            target["status"] = ranked["status"]
            target["beatmap_id"] = ranked["beatmap_id"]
            target["beatmapset_id"] = ranked["beatmapset_id"]
    report.note("Comparing verified player evidence")
    analyses = list({a.key: a for a in analyses}.values())
    analyses, unverified = verified_analyses(analyses)
    rows = domain.evidence(analyses, player)
    if rows:
        warnings.append(
            f"Latest available evidence: {max(str(r.get('date')) for r in rows)}. Estimates describe the available plays, not guaranteed current form."
        )
    if unverified:
        warnings.append(f"{unverified} older lazer analysis record(s) lack verifiable mod settings and are excluded.")
    if player is None:
        warnings.append("Choose one player on the Replays page; multiple players are never pooled for predictions.")
    if not rows:
        warnings.append(
            "Starter maps use an unmeasured 1.5-2 star starting assumption, not a measured skill level. Analyse your replays to personalize them."
        )
    owned = [a for a in analyses if a.meta.get("player") == player and domain.sim_ok(a.meta)]
    focus = domain.blockers(owned, target) if target else []
    if target:
        target["dynamics"] = domain.dynamics(target)
    if target and not focus:
        profile = ws.profile()
        skills = {
            k: v["score"] / 100
            for k, v in (profile.skills if profile else {}).items()
            if isinstance(v.get("score"), int | float)
        }
        focus = domain.lacking_focus(target, skills)
    if target:
        verdict, reasons, confidence = domain.reachability(target, rows)
        skipped = domain.skipped_attempts(analyses, rows, player, target)
        if skipped:
            reasons.append(skipped)
        if not any(a.meta.get("beatmap_md5") == target["md5"] and a.meta.get("player") == player for a in analyses):
            reasons.append("No attempts of this map found in your replays.")
        accuracy = domain.accuracy_range(target, rows)
    else:
        verdict = "Find maps" if request.goal == "farm" else f"Build your {request.training_mod} control"
        reasons = ["Matched to your verified plays with these mods."]
        confidence, accuracy = ("limited" if rows else "unassessed"), None
    report.note("Finding attainable next plays")
    mods = (
        request.farm_mods
        if request.goal == "farm"
        else [request.training_mod]
        if request.goal == "mod"
        else [request.mods]
    )
    profile = ws.profile()
    levels = profile.levels if profile else {}
    comfort = domain.number(levels.get("comfort_stars")) or domain.number(levels.get("level_stars"))
    recommendations = domain.recommend(
        pool, rows, request.goal, mods, client, target, focus, request.min_pp, comfort=comfort
    )
    if request.goal == "farm" and not any(r["_projected"] for r in recommendations):
        warnings.append(
            "Not enough comparable FC evidence for achievable PP forecasts. All PP below is conditional on the stated FC scenario."
        )
    if accuracy is None and target:
        warnings.append(
            "Accuracy estimate unavailable: needs at least 10 comparable completed plays across 5 distinct maps."
        )
    if not recommendations:
        warnings.append(
            "No covered maps fit these demands. Analyse more relevant replays or choose a different mod; no unrelated maps were substituted."
        )
    report.note("Finishing your play goals")
    return PlayGoalResult.model_validate(
        {
            "request": request,
            "evidence_revision": evidence_revision,
            "player": player,
            "status": "insufficient_evidence"
            if not rows
            else "partial"
            if not recommendations or (target and accuracy is None)
            else "assessed",
            "verdict": verdict,
            "tone": domain.VERDICT_TONES.get(verdict, "info"),
            "reasons": reasons,
            "confidence": confidence,
            "target": target,
            "accuracy": accuracy,
            "blockers": focus,
            "recommendations": recommendations,
            "warnings": warnings,
            "coverage_maps": len({r["md5"] for r in pool}),
            "replay_path": replay_path,
        }
    )

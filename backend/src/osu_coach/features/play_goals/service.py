"""The play goals flow: the target, the player's verified evidence, the assessment and the next plays."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple
from urllib.parse import urlsplit

from pydantic import ValidationError

from osu_coach.common.errors import ApiError, Invalid
from osu_coach.domain.numeric.values import finite_or_none
from osu_coach.domain.play_goals import evidence
from osu_coach.domain.play_goals.models import EvidenceRow, GoalPlay, MapRow
from osu_coach.domain.play_goals.reachability import reachability
from osu_coach.domain.play_goals.recommend import dynamics as strong_demands
from osu_coach.domain.play_goals.recommend import lacking_focus, recommend
from osu_coach.domain.player import PlaySummary
from osu_coach.domain.replays.eligibility import analysable
from osu_coach.features.play_goals import repository, texts
from osu_coach.features.play_goals.schemas import PlayGoalOptions, PlayGoalRequest, PlayGoalResult
from osu_coach.infra import summaries
from osu_coach.infra.jobs import Reporter
from osu_coach.infra.library import Library
from osu_coach.infra.replays.osr import lazer_info
from osu_coach.infra.uploads import known_replay

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace


def selected_player(ws: Workspace) -> str | None:
    saved = ws.settings().player
    players = {a.meta.player for a in ws.plays}
    if saved and saved != "*":
        return saved
    return next(iter(players)) if len(players) == 1 else None


def revision(ws: Workspace) -> str:
    settings = ws.settings()
    value = (
        [a.key for a in ws.plays],
        selected_player(ws),
        settings.replay_set,
        settings.level_override,
    )
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()[:16]


def pool_data() -> list[dict]:
    try:
        return repository.load_goal_pool()
    except (ValueError, OSError) as exc:
        raise ApiError(503, "goal_pool_unavailable", str(exc)) from exc


def options(ws: Workspace) -> PlayGoalOptions:
    last = ws.settings().play_goal_request
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
        players=sorted({a.meta.player for a in ws.plays}),
        evidence_plays=len(ws.plays),
        coverage_maps=len({r["md5"] for r in pool}),
    )


def validate_request(ws: Workspace, request: PlayGoalRequest) -> None:
    if request.goal == "fc":
        if request.replay_path:
            known_replay(request.replay_path, ws.cache_dir, (ws.library, ws.check_library))
        else:
            try:
                beatmap_id(request.beatmap or "")
            except ValueError as exc:
                raise Invalid(str(exc), "invalid_goal_beatmap") from exc


def goal_plays(plays: list[PlaySummary]) -> tuple[list[GoalPlay], int]:
    """The plays as the play goals read them; lazer plays get their mods with settings read back from the replay
    file, and those whose file can't be read are counted as unverified."""
    unverified, out = 0, []
    for play in plays:
        m = play.meta
        lazer_mods, verified = None, True
        if m.client == "lazer":
            verified = False
            path = m.source_path
            if path and Path(path).is_file():
                info = lazer_info(Path(path).read_bytes())
                if info is not None:
                    lazer_mods, verified = info.get("mods"), True
            if not verified:
                unverified += 1
        out.append(GoalPlay(play.key, m, play.events, play.stream_share, play.jump_share, lazer_mods))
    return out, unverified


class _ReplayTarget(NamedTuple):
    raw: bytes  # the map's .osu file
    client: str
    replay_path: str
    player: str | None
    attempts: list[PlaySummary]  # this replay and the player's other attempts of the map


def _replay_target(
    ws: Workspace, request: PlayGoalRequest, player: str | None, has_plays: bool, warnings: list[str], report: Reporter
) -> _ReplayTarget:
    """The target from a replay: analyse it and the player's other attempts of its map."""
    path = known_replay(request.replay_path or "", ws.cache_dir, (ws.library, ws.check_library))
    lib = ws.replay_library()
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
    if player is None and not has_plays:
        player = selected.meta.player
    attempts: list[PlaySummary] = []
    if player != selected.meta.player:
        warnings.append("This replay belongs to another player. Its misses are not used to diagnose your blockers.")
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
        attempts = summaries.summarize(ws.cache_dir, [selected, *others])
    map_path = lib.maps.get(ref["beatmap_md5"])
    if not map_path:
        raise Invalid("The target beatmap is missing.", "goal_map_unavailable")
    return _ReplayTarget(Path(map_path).read_bytes(), selected.meta.client, str(path), player, attempts)


def _target(ws: Workspace, raw: bytes, request: PlayGoalRequest, client: str, pool: list[dict], report: Reporter):
    """The target map in the requested mods, with its ranked status when the pool knows it."""
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
    return target


def _evidence_warnings(rows: list[EvidenceRow], unverified: int, player: str | None) -> list[str]:
    out = []
    if rows:
        out.append(
            f"Latest available evidence: {max(r.date for r in rows)}. Estimates describe the available plays, not guaranteed current form."
        )
    if unverified:
        out.append(f"{unverified} older lazer analysis record(s) lack verifiable mod settings and are excluded.")
    if player is None:
        out.append("Choose one player on the Replays page; multiple players are never pooled for predictions.")
    if not rows:
        out.append(
            "Starter maps use an unmeasured 1.5-2 star starting assumption, not a measured skill level. Analyse your replays to personalize them."
        )
    return out


def _focus(plays: list[GoalPlay], player: str | None, target: MapRow | None, profile) -> list[dict]:
    """What to train for the target: the skills behind the misses in the player's attempts, else the target's
    demands the player is weakest at."""
    if not target:
        return []
    owned = [a for a in plays if a.meta.player == player and evidence.sim_ok(a.meta)]
    found = [texts.blocker(b) for b in evidence.blockers(owned, target)]
    if found:
        return found
    skills = {
        k: v.score / 100
        for k, v in (profile.skill_ratings if profile else {}).items()
        if isinstance(v.score, int | float)
    }
    return [texts.lacking(k, skills) for k in lacking_focus(target, skills)]


def _assessment(request: PlayGoalRequest, target, rows: list[EvidenceRow], plays: list[GoalPlay], player: str | None):
    """The verdict, its tone, reasons and confidence, and the accuracy estimate for the target."""
    if not target:
        verdict = "Find maps" if request.goal == "farm" else f"Build your {request.training_mod} control"
        return (
            verdict,
            "info",
            ["Matched to your verified plays with these mods."],
            "limited" if rows else "unassessed",
            None,
        )
    reach = reachability(target, rows)
    reasons = [texts.reason(r) for r in reach.reasons]
    skipped = texts.skipped(evidence.skipped_attempts(plays, rows, player, target))
    if skipped:
        reasons.append(skipped)
    if not any(a.meta.beatmap_md5 == target["md5"] and a.meta.player == player for a in plays):
        reasons.append("No attempts of this map found in your replays.")
    tone = texts.TONES.get(reach.verdict, "info")
    return texts.VERDICTS[reach.verdict], tone, reasons, reach.confidence, evidence.accuracy_range(target, rows)


def evaluate(ws: Workspace, request: PlayGoalRequest, report: Reporter) -> PlayGoalResult:
    report.note("Preparing map and mod evidence")
    ws.update_settings(play_goal_request=request.model_dump())
    pool = pool_data()
    player = selected_player(ws)
    evidence_revision = revision(ws)
    plays = list(ws.plays)
    target, replay_path, client = None, None, request.client
    warnings = [
        f"Offline recommendations cover {len({r['md5'] for r in pool})} selected difficulties, not the entire osu! catalogue.",
        "PP values are conservative hit-result FC scenarios from the pinned calculator, not account PP gains. "
        "Accuracy rounding and slider outcomes can change PP.",
    ]
    if request.goal == "fc":
        if request.replay_path:
            found = _replay_target(ws, request, player, bool(plays), warnings, report)
            raw, client, replay_path, player = found.raw, found.client, found.replay_path, found.player
            plays.extend(found.attempts)
        else:
            report.note("Resolving the target difficulty")
            client = "lazer"
            libraries = [lib for lib in (ws.library, ws.check_library) if lib]
            raw = repository.target_bytes(
                ws.cache_dir, beatmap_id(request.beatmap or ""), libraries, request.online, pool
            )
        target = _target(ws, raw, request, client, pool, report)
    report.note("Comparing verified player evidence")
    analysed, unverified = goal_plays(list({a.key: a for a in plays}.values()))
    rows = evidence.evidence(analysed, player)
    warnings += _evidence_warnings(rows, unverified, player)
    profile = ws.profile()
    focus = _focus(analysed, player, target, profile)
    if target:
        target["dynamics"] = texts.dynamics(strong_demands(target))
    verdict, tone, reasons, confidence, accuracy = _assessment(request, target, rows, analysed, player)
    report.note("Finding attainable next plays")
    mods = (
        request.farm_mods
        if request.goal == "farm"
        else [request.training_mod]
        if request.goal == "mod"
        else [request.mods]
    )
    comfort = (
        finite_or_none(profile.levels.comfort_stars) or finite_or_none(profile.levels.level_stars) if profile else None
    )
    skills = [b["skill"] for b in focus]
    recommendations = recommend(pool, rows, request.goal, mods, client, target, skills, request.min_pp, comfort)
    if request.goal == "farm" and not any(r.projected for r in recommendations):
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
            "tone": tone,
            "reasons": reasons,
            "confidence": confidence,
            "target": target,
            "accuracy": texts.accuracy(accuracy),
            "blockers": focus,
            "recommendations": [texts.recommendation(r, focus) for r in recommendations],
            "warnings": warnings,
            "coverage_maps": len({r["md5"] for r in pool}),
            "replay_path": replay_path,
        }
    )


def beatmap_id(value: str) -> int:
    value = value.strip()
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.netloc != "osu.ppy.sh":
        raise ValueError("Use an https://osu.ppy.sh beatmap difficulty link.")
    match = re.fullmatch(r"/(?:b|beatmaps)/([1-9][0-9]{0,9})/?", parsed.path)
    if not match and re.fullmatch(r"/beatmapsets/[1-9][0-9]*/?", parsed.path):
        match = re.fullmatch(r"osu/([1-9][0-9]{0,9})", parsed.fragment)
    if not match:
        raise ValueError("Choose a specific osu!standard difficulty, not just a beatmapset.")
    return int(match[1])

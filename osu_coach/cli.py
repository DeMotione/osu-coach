"""Command line interface.

  osu-coach ui                         open the app in your browser
  osu-coach locate                     show detected osu! installs
  osu-coach analyze [--folder DIR]     analyse your replays, print stats + tips
  osu-coach playlist SKILL [...]       practice playlist (+ lazer import folder, collection.db, .osz)
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
import math
import subprocess
import sys
from pathlib import Path

from . import check, lazer_import, locate, progress, selection, sources
from .advice import Setup, make_tips, practice_plan
from .collection_db import merge_into, write_collection_db
from .library import EXCLUDE_MODS, Library, load_settings, save_settings, skip_reason
from .pool import SKILLS, Targets, build_playlist, collection_name, load_pool, recommendations, skill_label, \
    targets_from_profile
from .profile import MISS_LABELS, build_profile

SEVERITY = {3: "HIGH", 2: "MED ", 1: "LOW "}


def _num(v, spec=".1f", none="–") -> str:
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return none
        return format(v, spec)
    except (TypeError, ValueError):
        return str(v)


def _bar(score, width=20) -> str:
    if score is None:
        return "·" * width
    n = int(round(score / 100 * width))
    return "█" * n + "░" * (width - n)


def _setup_from(args) -> Setup:
    s = {k: v for k, v in load_settings(args.cache).items() if k in Setup.__dataclass_fields__}
    if getattr(args, "device", None):
        s["device"] = args.device
    if getattr(args, "area", None):
        w, _, h = args.area.lower().partition("x")
        s["area_w_mm"], s["area_h_mm"] = float(w), float(h)
    if getattr(args, "dpi", None):
        s["mouse_dpi"] = args.dpi
    if getattr(args, "rapid_trigger", False):
        s["keyboard"] = "rapid_trigger"
    return Setup(**s)


def _discover(args, log) -> Library:
    lib = Library(args.cache)
    if getattr(args, "only", None):
        files = [Path(f) for f in args.only]
        missing = [str(f) for f in files if not f.is_file()]
        if missing:
            raise SystemExit("File not found: " + ", ".join(missing))
        log(f"analysing only {len(files)} file(s)")
        lib.add_files(files, source="file")
        if not args.no_auto:            # their beatmaps may be in the osu! installs or the folders
            for inst in locate.find_installs():
                lib.add_map_source(inst)
        for f in args.folder or []:
            lib.add_folder(f, maps_only=True)
        return lib
    latest = args.limit or None
    if latest:
        log(f"reading only the newest {latest} replays" + (f" of {args.player}" if args.player else ""))
    if not args.no_auto:
        for inst in locate.find_installs():
            log(f"found {inst.label}")
            lib.add_install(inst, progress=log, latest=latest, player=args.player)
    for f in args.folder or []:
        lib.add_folder(f, latest=latest, player=args.player)
    return lib


def _analyse(args, log):
    lib = _discover(args, log)
    players = lib.players()
    if not players:
        raise SystemExit("No osu!standard replays found. Point --folder at a folder with .osr files "
                         "(stable: osu!/Data/r, lazer: export replays from the results screen).")
    player = args.player or players[0][0]
    refs = lib.eligible(player)
    since, until = _date_window(args, refs)
    refs = selection.filter_refs(refs, since, until)[:args.limit or None]
    if since or until:
        log("played " + (f"from {since:%Y-%m-%d %H:%M} UTC " if since else "") + (f"until {until:%Y-%m-%d} " if until else ""))
    if not refs and (since or until):
        raise SystemExit(f"No replays of '{player}' in that time range.")
    if not refs:
        raise SystemExit(f"No replays for player '{player}'. Players found: "
                         + ", ".join(f"{p} ({n})" for p, n in players))
    missing = lib.missing_maps(refs, progress=log)
    if missing and not args.offline:
        log(f"downloading {len(missing)} missing beatmap(s)…")
        lib.fetch_missing(missing)

    def analysed(done, total, _msg):
        if done == total or done % 10 == 0:
            log(f"analysed {done}/{total}")
    analyses, errors = lib.analyze(refs, workers=args.workers, progress=analysed)
    for ref, err in errors[:5]:
        log(f"skipped {Path(ref['path']).name}: {err}")
    if not analyses:
        raise SystemExit("None of the replays could be analysed.")
    log("saving your progress by month…")
    try:
        progress.update(lib.cache, analyses, lib.load_cached)
    except Exception as exc:  # noqa: BLE001 - the report matters more than the history
        log(f"could not save progress: {exc}")
    replay_set = _replay_set(args)
    chosen = selection.select(analyses, replay_set)
    if not chosen:
        raise SystemExit("No passed plays among these replays — use --all-replays.")
    if replay_set == "best":
        log(f"best replays: {len(chosen)} of {len(analyses)}")
    return lib, player, analyses, errors, build_profile(chosen, level=getattr(args, "level", None))


def _replay_set(args) -> str:
    """--best / --all-replays, else the choice saved by the app (remembered there and here)."""
    if getattr(args, "replay_set", None):
        sett = load_settings(args.cache)
        if sett.get("replay_set") != args.replay_set:
            sett["replay_set"] = args.replay_set
            save_settings(sett, args.cache)
        return args.replay_set
    saved = load_settings(args.cache).get("replay_set")
    return saved if saved in selection.REPLAY_SETS else "all"


def _date_window(args, refs):
    since_arg = getattr(args, "since", None)
    until_arg = getattr(args, "until", None)
    if not since_arg and not until_arg:
        return None, None
    import datetime as dt

    def day(v):
        try:
            return dt.date.fromisoformat(v)
        except ValueError:
            raise SystemExit(f"Not a date (YYYY-MM-DD): {v}") from None
    if since_arg in ("session", "7d", "30d"):
        since, _ = selection.date_window(since_arg, [r.get("timestamp") for r in refs])
    else:
        since, _ = selection.date_window("custom", start=day(since_arg)) if since_arg else (None, None)
    until = selection.date_window("custom", end=day(until_arg))[1] if until_arg else None
    return since, until


def _log(quiet):
    return (lambda *_: None) if quiet else (lambda msg: print(f"  … {msg}", file=sys.stderr))


# ------------------------------------------------------------------ commands
def cmd_locate(args) -> int:
    installs = locate.find_installs()
    if not installs:
        print("No osu! installation found automatically.\n"
              "Use --folder with `analyze` (stable: <osu!>/Data/r, lazer: export replays).")
        return 0
    for inst in installs:
        print(inst.label)
        if inst.songs:
            print(f"  songs:        {inst.songs}")
        for d in inst.replay_dirs:
            print(f"  replays:      {d} ({sum(1 for _ in d.glob('*.osr'))} files)")
        if inst.files_dir:
            print(f"  file store:   {inst.files_dir}")
        if inst.collection_db:
            print(f"  collections:  {inst.collection_db}")
    return 0


def cmd_analyze(args) -> int:
    lib, player, analyses, errors, prof = _analyse(args, _log(args.quiet))
    setup = _setup_from(args)
    tips = make_tips(prof, setup)
    ov, lv = prof.overview, prof.levels
    replay_set = _replay_set(args)
    if args.json:
        out = {"player": player, "overview": ov, "levels": {k: v for k, v in lv.items() if k != "model_coef"},
               "skills": prof.skills, "strengths": prof.strengths, "weaknesses": prof.weaknesses,
               "miss_breakdown": prof.miss_breakdown, "tapping": prof.tapping, "aim": prof.aim,
               "worst_quadrant": prof.worst_quadrant, "regression": prof.regression,
               "tips": [t.to_dict() for t in tips], "practice_plan": practice_plan(prof)}
        Path(args.json).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"wrote {args.json}")
    which = "best " if replay_set == "best" else ""
    print(f"\nosu-coach report — {player}: {ov['replays']} {which}{'newest ' if args.limit else ''}replays on "
          f"{ov['maps']} maps, "
          f"{_num(ov['play_minutes'], '.0f')} min of play")
    if replay_set == "best":
        print(f"  ({selection.BEST_DEFINITION})")
    lvl = lv.get("level_stars")
    how = ("set with --level" if lv.get("level_override") else
           f"detected from your {lv.get('level_recent_n', 0)} most recent replays")
    print(f"Level {_num(lvl, '.2f')}★ ({how}): replays within ±{lv.get('level_band', 0.5):g}★ count fully, the "
          f"further away the less (weighted replays: {ov.get('weighted_replays', 0):.1f} of {ov['replays']})")
    print(f"Comfort level ≈ {_num(lv.get('comfort_stars'), '.1f')}★ | UR {_num(ov['ur'], '.0f')} | "
          f"{_num(ov['misses_per_100'], '.1f')} misses per 100 notes | accuracy {_num(ov['accuracy'] * 100, '.1f')}%")
    print(f"Judgement check: re-simulated results match the replay exactly on {ov['sim_exact_share']:.0%} of "
          f"replays ({ov['sim_agreement']:.1%} of judgements)")
    print("\nSkills (50 = as many misses as expected for the difficulty; higher is better)")
    for k, s in prof.skills.items():
        score = s.get("score")
        note = f"{_num(score, '.0f'):>3}" if score is not None else "  ?"
        print(f"  {s['label']:<32} {_bar(score)} {note}  ({s.get('n', 0)} notes"
              + (", too few misses to tell)" if s.get("too_few_misses") else ")"))
    print("Strengths: " + (", ".join(prof.skills[k]["label"] for k in prof.strengths) or "–"))
    print("Work on:   " + (", ".join(prof.skills[k]["label"] for k in prof.weaknesses) or "–"))
    total = sum(prof.miss_breakdown.values())
    if total:
        raw = prof.miss_breakdown_raw
        print(f"\nWhy you miss ({sum(raw.values())} misses; shares weighted by difficulty)")
        for reason, n in sorted(prof.miss_breakdown.items(), key=lambda kv: -kv[1]):
            print(f"  {raw.get(reason, 0):>5}  {n / total:4.0%}  {MISS_LABELS.get(reason, reason)}")
    fb = prof.fall_behind or {}
    if fb.get("start_note"):
        secs = f" (≈ {fb['start_seconds']:.1f} s at {fb['bpm']:.0f} BPM)" if fb.get("start_seconds") is not None else ""
        print(f"Long streams: your precision starts to drop after about {fb['start_note']} notes{secs}: "
              f"{fb['base_ms']:.0f} ms off on average before, +{fb['growth_ms']:.0f} ms by the end. Comfortable "
              f"stream length ≈ {fb['comfort_notes']} notes; practise {fb['practice_notes'][0]}–"
              f"{fb['practice_notes'][1]}.")
    elif fb.get("comfort_notes"):
        print(f"Long streams: your precision holds up to {fb['comfort_notes']} notes (the longest measured); "
              f"practise {fb['practice_notes'][0]}–{fb['practice_notes'][1]} notes.")
    print("\nTips (most important first)")
    for t in tips[: args.tips]:
        print(f"\n [{SEVERITY.get(t.severity, '')}] {t.category}: {t.title}")
        print(f"        {t.evidence}")
        for a in t.actions:
            print(f"        - {a}")
    print("\nPractice plan")
    for i, step in enumerate(practice_plan(prof), 1):
        print(f"  {i}. {step}")
    pool = load_pool()
    if not pool.empty:
        t = targets_from_profile(prof)
        print("\nMap Suggestion")
        for sk, df in recommendations(pool, prof, per_skill=3, ranking=getattr(args, "ranking", "weighted")):
            print(f"  {skill_label(sk, t)}:")
            for _, r in df.iterrows():
                print(f"    {r['stars']:.2f}★  {r['artist']} - {r['title']} [{r['version']}]  · {r['why']}\n"
                      f"           {r['url']}")
    if errors:
        reasons = Counter(err.removeprefix("skipped: ") for _, err in errors)
        print(f"\n{len(errors)} replay(s) skipped: " + "; ".join(f"{n}× {r}" for r, n in reasons.most_common(4)))
    refs = lib.eligible(player, args.limit) if args.limit and not getattr(args, "only", None) else []
    left = lib.left_out(player, since=refs[-1]["timestamp"] if refs else None)
    if left:
        print(("" if errors else "\n") + f"{sum(left.values())} replay(s) left out: "
              + "; ".join(f"{n}× {r}" for r, n in left.most_common(4)))
    return 0


def cmd_playlist(args) -> int:
    pool = load_pool()
    if pool.empty:
        raise SystemExit("Map pool is missing (osu_coach/data/pool.json.gz).")
    lib = None
    if args.comfort:
        t = Targets(comfort=args.comfort, stream_bpm=args.stream_bpm, ranking=args.ranking)
    else:
        lib, *_, prof = _analyse(args, _log(args.quiet))
        t = targets_from_profile(prof)
        t.ranking = args.ranking
        if args.stream_bpm:
            t.stream_bpm = args.stream_bpm
    if args.skill == "quadrant" and not t.quadrant:
        raise SystemExit("No clearly weak quadrant in your replays — pick another skill.")
    pl = build_playlist(pool, args.skill, t, n=args.maps)
    name = collection_name(args.skill, t)
    print(f"{name} — {len(pl)} maps (your level ≈ {t.comfort:.1f}★)")
    for stage, part in pl.groupby("stage", sort=False):
        print(f"\n{stage}: {part['goal'].iloc[0]}")
        for _, r in part.iterrows():
            print(f"  {r['stars']:.2f}★  {r['artist']} - {r['title']} [{r['version']}]  · {r['why']}\n"
                  f"         {r['url']}")
    hashes = list(pl["md5"])
    if args.lazer:
        dest = Path(args.lazer) if isinstance(args.lazer, str) else lazer_import.default_pack_dir(name)
        if lib is not None and lib.has_unread_maps("lazer"):
            lib.find_maps(set(hashes))       # which playlist maps lazer already has
        have = lib.installed["lazer"] if lib is not None else set()
        sets = [] if args.no_maps else lazer_import.sets_to_download(zip(pl["md5"], pl["beatmapset_id"]), have)
        log = _log(args.quiet)
        res = lazer_import.build_pack(dest, {name: hashes}, sets, progress=lambda i, n, msg: log(msg))
        print(f"\nlazer import folder: {res['path']}  ({len(res['maps'])} map set(s) + the collection)")
        if res["failed"]:
            print(f"  couldn't download set(s) {', '.join(map(str, res['failed']))} — use the links above")
        for i, step in enumerate(lazer_import.INSTRUCTIONS, 1):
            print(f"  {i}. {step.replace('**', '').replace('*', '')}")
    if args.collection:
        p = write_collection_db(args.collection, {name: hashes})
        print(f"\nwrote {p}\n  lazer: use --lazer instead (lazer can't open a collection.db on its own)\n"
              "  stable: use --merge (with osu! closed) or Collection Manager")
    if args.merge:
        st = [i for i in locate.find_installs() if i.kind == "stable"]
        if not st:
            raise SystemExit("No osu!stable install found to merge into.")
        if locate.is_osu_running():
            raise SystemExit("Close osu! first — it rewrites collection.db when it exits.")
        info = merge_into(st[0].root / "collection.db", {name: hashes})
        print(f"\nadded to {info['path']} (backup: {info['backup']})")
    if args.download:
        dest = Path(args.download)
        sets = list(dict.fromkeys(int(s) for s in pl["beatmapset_id"]))
        ok = 0
        for i, sid in enumerate(sets, 1):
            got = sources.download_osz(sid, dest)
            ok += bool(got)
            print(f"  [{i}/{len(sets)}] {sid}: {'ok ' + got.name if got else 'failed'}")
        print(f"downloaded {ok}/{len(sets)} beatmap sets to {dest}")
    return 0


PROGRESS_COLUMNS = [  # (header, column, format)
    ("Plays", "plays", "{:.0f}"), ("Maps", "maps", "{:.0f}"), ("New", "new_maps", "{:.0f}"), ("Min", "minutes", "{:.0f}"),
    ("Comfort★", "comfort_stars", "{:.2f}"), ("Avg★", "avg_stars", "{:.2f}"), ("Passed★", "max_stars_passed", "{:.2f}"),
    ("FC★", "max_stars_fc", "{:.2f}"), ("Acc%", "accuracy", "{:.2%}"), ("UR", "ur", "{:.0f}"),
    ("BPM", "stream_bpm", "{:.0f}"), ("Aim", "skill_aim", "{:.0f}"), ("Flow", "skill_flow_aim", "{:.0f}"),
    ("Speed", "skill_speed", "{:.0f}"), ("Stam", "skill_stamina", "{:.0f}"), ("AccSk", "skill_accuracy", "{:.0f}"),
    ("Slid", "skill_sliders", "{:.0f}"), ("Read", "skill_reading", "{:.0f}"), ("Cons", "skill_consistency", "{:.0f}"),
]


def cmd_progress(args) -> int:
    conn = progress.connect(args.cache)
    try:
        names = progress.players(conn)
        if not names:
            print("Nothing saved yet: run `osu-coach analyze` first — every analysis is saved by month.")
            return 0
        player = args.player if args.player is not None else names[0][0]
        m = progress.monthly(conn, player)
    finally:
        conn.close()
    if m.empty:
        print(f"Nothing saved for '{player}'. Players: " + ", ".join(f"{p} ({n})" for p, n in names))
        return 0
    print(f"Progress — {player or '(no name)'}: {int(m['plays'].sum())} plays in {len(m)} "
          f"month{'' if len(m) == 1 else 's'} "
          f"(saved in {progress.db_path(args.cache)})\n")
    widths = [max(len(h), 6) for h, _, _ in PROGRESS_COLUMNS]
    print("Month    " + " ".join(h.rjust(w) for (h, _, _), w in zip(PROGRESS_COLUMNS, widths)))
    for _, row in m.iterrows():
        cells = []
        for (_, col, fmt), w in zip(PROGRESS_COLUMNS, widths):
            v = row.get(col)
            cells.append(("–" if v is None or (isinstance(v, float) and math.isnan(v)) else fmt.format(v)).rjust(w))
        print(f"{row['month']}{'*' if row['few_plays'] else ' '} " + " ".join(cells))
    print("\n* fewer than 5 plays that month (no skill numbers then). Comfort★ = 75% of your clean finished plays "
          "(≤ 2 misses per 100 notes) are at or below it. Passed★ = hardest map finished with ≤ 5 misses per 100 "
          "notes. Skills (Aim … Cons): 50 = your all-time average at the same difficulty, higher = fewer misses "
          "than usual that month.")
    return 0


EVENTS_SHOWN = 40


def _main_player(lib: Library, cache) -> str | None:
    """Whose newest replay to check: the player saved in the settings or with the most saved plays."""
    saved = load_settings(cache).get("player")
    if saved and saved != "*":
        return saved
    conn = progress.connect(cache)
    try:
        names = progress.players(conn)
    finally:
        conn.close()
    return names[0][0] if names else None


def cmd_check(args) -> int:
    log = _log(args.quiet)
    lib = Library(args.cache)
    path = Path(args.replay) if args.replay else None
    if path is not None:
        if not path.is_file():
            raise SystemExit(f"File not found: {path}")
        lib.add_files([path], source="file")
    player = args.player or (None if path else _main_player(lib, args.cache))
    latest = 1 if player or path else 20     # unknown player: read a few replays to see who plays here
    if not args.no_auto:
        for inst in locate.find_installs():
            lib.add_install(inst, progress=log, latest=latest, player=player)
    for f in args.folder or []:
        lib.add_folder(f, latest=latest, player=player)
    if path is not None:
        ref = next((r for r in lib.replays if Path(r["path"]) == path), None)
        if ref is None:
            raise SystemExit(f"Not an osu! replay: {path}")
    else:
        players = lib.players()
        if not players:
            raise SystemExit("No osu!standard replays found. Give a replay file, or point --folder at your replays.")
        player = player if player in dict(players) else players[0][0]
        ref = lib.eligible(player, 1)[0]
    if ref.get("mode") != 0:
        raise SystemExit("Only osu!standard replays can be checked.")
    if ref.get("mods", 0) & EXCLUDE_MODS:
        raise SystemExit("Relax / autopilot / autoplay replays aren't checked.")
    if skip_reason(ref):
        raise SystemExit(f"Can't check this replay: {skip_reason(ref)}.")
    missing = lib.missing_maps([ref], progress=log)
    if missing and not args.offline:
        log("downloading the beatmap…")
        lib.fetch_missing(missing)
    analyses, errors = lib.analyze([ref], workers=1)
    if not analyses:
        raise SystemExit(f"Can't check {Path(ref['path']).name}: {errors[0][1] if errors else 'unknown error'}")
    a = analyses[0]
    same = [r for r in lib.replays if r.get("beatmap_md5") == ref.get("beatmap_md5") and r.get("mode") == 0
            and not (r.get("mods", 0) & EXCLUDE_MODS) and not skip_reason(r)
            and (r.get("player") or "") == (ref.get("player") or "") and str(r["path"]) != str(ref["path"])]
    others, _ = lib.analyze(same[:50]) if same else ([], [])
    conn = progress.connect(lib.cache)
    try:
        cmp = check.compare(conn, a, others)
        progress.record(conn, [a] + list(others))
    finally:
        conn.close()
    _print_check(a, cmp)
    return 0


def _print_check(a, cmp: dict) -> None:
    ev = check.events(a)
    s = check.summary(a, ev)
    m = a.meta
    length = s["length_s"] or 0
    rate = s["rate"] or 1.0
    mods = check.mods_label(s["mods"], rate)
    print(f"\nDetailed map analysis — {s['player'] or '(no name)'}, {check.local_time(s['date'])} (osu!{s['client']})")
    print(f"{s['map']} · {mods} · {s['stars'] or 0:.2f}★ · {s['bpm'] or 0:.0f} BPM · "
          f"{int(length // 60)}:{int(length % 60):02d} · {check.settings_label(m) or 'normal speed'}"
          + (f" · UR {s['ur']:.0f}" if not check._nan(s["ur"]) else ""))
    combo = f"{s['combo']}/{s['map_combo']:.0f}x" if not check._nan(s["map_combo"]) else f"{s['combo']}x"
    n300, n100, n50, nmiss = s["counts"]
    print(f"{s['accuracy']:.2%} · {combo} · 300/100/50/miss {n300}/{n100}/{n50}/{nmiss}"
          + ("" if s["completed"] else " · FAILED"))
    if m.get("beatmap_id"):
        print(f"https://osu.ppy.sh/b/{m['beatmap_id']}")
    print()
    for v in s["verdict"]:
        print(f"  {v}")
    if not s["sim_exact"]:
        print(f"  (The re-simulation differs a little from the result stored in the replay: "
              f"{(s['sim_agreement'] or 0):.1%} agreement — times may be slightly off.)")
    print("\nMisses and combo breaks")
    if ev.empty:
        print("  none")
    for r in ev.head(EVENTS_SHOWN).to_dict("records"):
        pat = check.pattern_label(r["pattern"], r["stream_bpm"])
        print(f"  {r['timestamp']}  {r['what']:<12} {check.REASON_WORDS.get(r['reason'], r['reason']):<15} "
              f"{r['detail']}{' · ' + pat if pat else ''}")
    if len(ev) > EVENTS_SHOWN:
        print(f"  … and {len(ev) - EVENTS_SHOWN} more")
    secs = check.practice_sections(a, ev)
    if secs:
        print("\nWhere they cluster — parts to practise (cut them out in the editor)")
        for x in secs[:5]:
            pat = check.PATTERN_WORDS.get(x["pattern"], x["pattern"] or "")
            bpm = f" {x['bpm']:.0f} BPM" if x["bpm"] and x["pattern"] in ("stream", "burst") else ""
            reasons = ", ".join(f"{n} {check.REASON_WORDS.get(k, k)}" for k, n in
                                sorted(x["reasons"].items(), key=lambda kv: -kv[1]))
            print(f"  {check.timestamp(x['start'])}–{check.timestamp(x['end'])}  {x['seconds']:.1f} s, "
                  f"{x['notes']} notes · {x['count']}: {reasons}" + (f" · {pat}{bpm}" if pat else ""))
    print("\nYour plays of this map")
    settings = cmp.get("settings") or "normal speed"
    if cmp["map_plays"]:
        best = "this is your best with these settings" if cmp["map_best"] else "not your best with these settings"
        print(f"  Same settings ({settings}): {cmp['map_plays']} other play(s), best {cmp['map_best_misses']} misses "
              f"({cmp['map_best_accuracy']:.2%}) — {best}.")
    else:
        print(f"  First play with these settings ({settings}).")
    if cmp.get("other_settings"):
        print(f"  {cmp['other_settings']} play(s) with other settings (speed, AR/OD/CS/HP, HD/FL) aren't compared.")


def cmd_ui(args) -> int:
    app = Path(__file__).parent / "webapp" / "app.py"
    # localhost only: the app reads and writes local files, so it must not be reachable from the network
    # (also avoids the Windows firewall prompt on first start)
    cmd = [sys.executable, "-m", "streamlit", "run", str(app), "--server.port", str(args.port),
           "--server.address", "localhost",
           "--browser.gatherUsageStats", "false", "--client.toolbarMode", "viewer",
           "--theme.light.primaryColor", "#e0408a", "--theme.dark.primaryColor", "#ff66aa"]
    # only the accent colour, separately for light and dark: a fixed base / background / text colour turns
    # Streamlit's theme into one custom theme, and its Settings → light / dark switch stops working.
    if args.no_browser:
        cmd += ["--server.headless", "true"]
    return subprocess.call(cmd)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="osu-coach", description="Analyse your osu! replays and get coaching.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def discovery(p):
        p.add_argument("--folder", action="append", help="extra folder with .osr/.osu files (repeatable)")
        p.add_argument("--no-auto", action="store_true", help="don't look for osu! installs automatically")
        p.add_argument("--player", help="player name (default: the one with most replays)")
        p.add_argument("--limit", "--latest", type=int, metavar="N",
                       help="only your newest N replays (e.g. 100, 500, 1000): only those are read and analysed")
        p.add_argument("--since", metavar="WHEN",
                       help="only replays played since: session (your last session), 7d, 30d or a date YYYY-MM-DD")
        p.add_argument("--until", metavar="DATE", help="only replays played up to this date (YYYY-MM-DD, included)")
        sel = p.add_mutually_exclusive_group()
        sel.add_argument("--best", dest="replay_set", action="store_const", const="best",
                         help="Best replays: only passed plays, and for every beatmap + speed mod (NM, DT, HT, rate) "
                              "only the best one (highest score, then accuracy). Remembered, like the app's switch")
        sel.add_argument("--all-replays", dest="replay_set", action="store_const", const="all",
                         help="All replays (default; remembered)")
        p.add_argument("--level", type=float, metavar="STARS",
                       help="your level for the difficulty weighting (default: detected from your recent replays)")
        p.add_argument("--only", action="append", metavar="REPLAY.osr",
                       help="analyse only these replay files (repeatable), not your library")
        p.add_argument("--offline", action="store_true", help="don't download missing beatmaps")
        p.add_argument("--workers", type=int, help="parallel analysis processes")
        p.add_argument("--cache", help="cache folder (default: per-user cache dir)")
        p.add_argument("-q", "--quiet", action="store_true")

    p = sub.add_parser("ui", help="open the app")
    p.add_argument("--port", type=int, default=8501)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_ui)
    p = sub.add_parser("locate", help="show detected osu! installs")
    p.set_defaults(func=cmd_locate)
    p = sub.add_parser("analyze", help="analyse replays and print the report")
    discovery(p)
    p.add_argument("--json", help="also write the full report as JSON")
    p.add_argument("--tips", type=int, default=8, help="number of tips to print")
    p.add_argument("--ranking", choices=["weighted", "cocoso"], default="weighted",
                   help="how suggested maps are ordered (cocoso = balanced across all criteria)")
    p.add_argument("--device", choices=["tablet", "mouse"])
    p.add_argument("--area", help="tablet area in mm, e.g. 100x56.25")
    p.add_argument("--dpi", type=int, help="mouse DPI")
    p.add_argument("--rapid-trigger", action="store_true", help="you use a rapid-trigger keyboard")
    p.set_defaults(func=cmd_analyze)
    p = sub.add_parser("playlist", help="Skill Development: practice playlist for one skill")
    p.add_argument("skill", choices=SKILLS + ["quadrant", "general"])
    discovery(p)
    p.add_argument("--comfort", type=float, help="your comfortable star rating (skips replay analysis)")
    p.add_argument("--stream-bpm", type=float, help="stream speed to train at")
    p.add_argument("--maps", type=int, default=15)
    p.add_argument("--ranking", choices=["weighted", "cocoso"], default="weighted",
                   help="how maps are ordered (cocoso = balanced across all criteria)")
    p.add_argument("--lazer", nargs="?", const=True, metavar="DIR",
                   help="make a folder for lazer's 'import from previous version' with the maps and the collection "
                        "(default: Downloads/osu-coach lazer import/<playlist>)")
    p.add_argument("--no-maps", action="store_true", help="with --lazer: only the collection, no map downloads")
    p.add_argument("--collection", help="write a collection.db with the playlist")
    p.add_argument("--merge", action="store_true", help="add the playlist to your osu!stable collections")
    p.add_argument("--download", help="download the maps (.osz) into this folder")
    p.set_defaults(func=cmd_playlist)
    p = sub.add_parser("check", help="check one replay: misses with timestamps, sections, compared with usual")
    p.add_argument("replay", nargs="?", help=".osr file (default: your newest replay)")
    p.add_argument("--folder", action="append", help="extra folder with .osr/.osu files (repeatable)")
    p.add_argument("--no-auto", action="store_true", help="don't look for osu! installs automatically")
    p.add_argument("--player", help="whose newest replay (default: you — the player with most replays)")
    p.add_argument("--offline", action="store_true", help="don't download a missing beatmap")
    p.add_argument("--cache", help="data folder (default: per-user cache dir)")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("progress", help="your progress by month (every analysis is saved)")
    p.add_argument("--player", help="player name (default: the one with most saved plays)")
    p.add_argument("--cache", help="data folder (default: per-user cache dir)")
    p.set_defaults(func=cmd_progress)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not hasattr(args, "cache"):
        args.cache = None
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

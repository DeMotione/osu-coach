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

from . import lazer_import, locate, progress, sources
from .advice import Setup, make_tips, practice_plan
from .collection_db import merge_into, write_collection_db
from .library import Library, load_settings
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
    refs = lib.eligible(player, args.limit)
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
    return lib, player, analyses, errors, build_profile(analyses)


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
    if args.json:
        out = {"player": player, "overview": ov, "levels": {k: v for k, v in lv.items() if k != "model_coef"},
               "skills": prof.skills, "strengths": prof.strengths, "weaknesses": prof.weaknesses,
               "miss_breakdown": prof.miss_breakdown, "tapping": prof.tapping, "aim": prof.aim,
               "worst_quadrant": prof.worst_quadrant, "regression": prof.regression,
               "tips": [t.to_dict() for t in tips], "practice_plan": practice_plan(prof)}
        Path(args.json).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"wrote {args.json}")
    print(f"\nosu-coach report — {player}: {ov['replays']} {'newest ' if args.limit else ''}replays on "
          f"{ov['maps']} maps, "
          f"{_num(ov['play_minutes'], '.0f')} min of play")
    print(f"Comfort level ≈ {_num(lv.get('comfort_stars'), '.1f')}★ | UR {_num(ov['ur'], '.0f')} | "
          f"{_num(ov['misses_per_100'], '.1f')} misses per 100 notes | accuracy {_num(ov['accuracy'] * 100, '.1f')}%")
    print(f"Judgement check: re-simulated results match the replay exactly on {ov['sim_exact_share']:.0%} of "
          f"replays ({ov['sim_agreement']:.1%} of judgements)")
    print("\nSkills (50 = as many misses as expected for the difficulty; higher is better)")
    for k, s in prof.skills.items():
        score = s.get("score")
        note = f"{_num(score, '.0f'):>3}" if score is not None else "  ?"
        print(f"  {s['label']:<32} {_bar(score)} {note}  ({s.get('n', 0)} notes)")
    print("Strengths: " + (", ".join(prof.skills[k]["label"] for k in prof.strengths) or "–"))
    print("Work on:   " + (", ".join(prof.skills[k]["label"] for k in prof.weaknesses) or "–"))
    total = sum(prof.miss_breakdown.values())
    if total:
        print(f"\nWhy you miss ({total} misses)")
        for reason, n in sorted(prof.miss_breakdown.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>5}  {n / total:4.0%}  {MISS_LABELS.get(reason, reason)}")
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
        print("\nSuggested maps")
        for sk, df in recommendations(pool, prof, per_skill=3):
            print(f"  {skill_label(sk, t)}:")
            for _, r in df.iterrows():
                print(f"    {r['stars']:.2f}★  {r['artist']} - {r['title']} [{r['version']}]  · {r['why']}\n"
                      f"           {r['url']}")
    if errors:
        reasons = Counter(err.removeprefix("skipped: ") for _, err in errors)
        print(f"\n{len(errors)} replay(s) skipped: " + "; ".join(f"{n}× {r}" for r, n in reasons.most_common(4)))
    refs = lib.eligible(player, args.limit) if args.limit else []
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
        t = Targets(comfort=args.comfort, stream_bpm=args.stream_bpm)
    else:
        lib, *_, prof = _analyse(args, _log(args.quiet))
        t = targets_from_profile(prof)
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


def cmd_ui(args) -> int:
    app = Path(__file__).parent / "webapp" / "app.py"
    # localhost only: the app reads and writes local files, so it must not be reachable from the network
    # (also avoids the Windows firewall prompt on first start)
    cmd = [sys.executable, "-m", "streamlit", "run", str(app), "--server.port", str(args.port),
           "--server.address", "localhost",
           "--browser.gatherUsageStats", "false", "--client.toolbarMode", "viewer", "--theme.base", "dark",
           "--theme.primaryColor", "#ff66aa",
           "--theme.backgroundColor", "#16161d", "--theme.secondaryBackgroundColor", "#22222c",
           "--theme.textColor", "#e8e8f0"]
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
    p.add_argument("--device", choices=["tablet", "mouse"])
    p.add_argument("--area", help="tablet area in mm, e.g. 100x56.25")
    p.add_argument("--dpi", type=int, help="mouse DPI")
    p.add_argument("--rapid-trigger", action="store_true", help="you use a rapid-trigger keyboard")
    p.set_defaults(func=cmd_analyze)
    p = sub.add_parser("playlist", help="practice playlist for one skill")
    p.add_argument("skill", choices=SKILLS + ["quadrant", "general"])
    discovery(p)
    p.add_argument("--comfort", type=float, help="your comfortable star rating (skips replay analysis)")
    p.add_argument("--stream-bpm", type=float, help="stream speed to train at")
    p.add_argument("--maps", type=int, default=15)
    p.add_argument("--lazer", nargs="?", const=True, metavar="DIR",
                   help="make a folder for lazer's 'import from previous version' with the maps and the collection "
                        "(default: Downloads/osu-coach lazer import/<playlist>)")
    p.add_argument("--no-maps", action="store_true", help="with --lazer: only the collection, no map downloads")
    p.add_argument("--collection", help="write a collection.db with the playlist")
    p.add_argument("--merge", action="store_true", help="add the playlist to your osu!stable collections")
    p.add_argument("--download", help="download the maps (.osz) into this folder")
    p.set_defaults(func=cmd_playlist)
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

"""Reference replays: what the skill scores give near-perfect plays, skill by skill.

    python dev_tools/reference_analysis.py [FOLDER] [--out OUT.json]

FOLDER (default ``reference_replays/`` in the project) holds the .osr files of the plays listed in
``dev_tools/reference_replays.json`` (any file names, any sub-folders). Each replay is matched to its skill by
the map's MD5, its .osu is downloaded once (cached in ``reference_replays/maps/``), and every play is
analysed with the same code as the player's own replays.

Printed per skill group: every play (player, map, mods, accuracy, misses) and, for the group, the skill
scores the current formulas give (``build_profile`` of the 5 plays, unweighted) plus the raw numbers behind
the skill — misses vs expected, 300 share / UR, slider breaks, miss-after-miss ratio, stamina parts and
steadiness. A near-perfect play of a skill should land near 100 on that skill; where it doesn't, the raw
numbers show which yardstick (``_score_from_ratio`` scale, ``STAMINA_WINDOW_SHARE``, the 300-share or ``SLIDER_REF``
scale, ``TYPICAL_CHAIN_RATIO``) needs moving. Use ``--out`` to keep the numbers for before/after checks.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from osu_coach.beatmaps import sources  # noqa: E402
from osu_coach.library.repository import analyze_bytes  # noqa: E402
from osu_coach.replays.osr import parse_replay  # noqa: E402
from osu_coach.profile.domain import SKILL_LABELS, build_profile  # noqa: E402

SKILL_KEY = {"aim": "aim", "flow": "flow_aim", "speed": "speed", "stamina": "stamina", "acc": "accuracy",
             "slider": "sliders", "reading": "reading", "cons": "consistency"}


def _r(v, d=1):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else round(v, d)


def load_osu(md5: str, cache: Path) -> bytes | None:
    f = cache / f"{md5}.osu"
    if f.exists():
        return f.read_bytes()
    got = sources.fetch_beatmap_by_md5(md5)
    if not got:
        return None
    cache.mkdir(parents=True, exist_ok=True)
    f.write_bytes(got[0])
    return got[0]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default=str(ROOT / "reference_replays"))
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    folder = Path(args.folder)
    refs = json.loads((ROOT / "dev_tools" / "reference_replays.json").read_text(encoding="utf-8"))
    by_md5 = defaultdict(list)
    for r in refs:
        by_md5[r["checksum"]].append(r)
    files = sorted(folder.rglob("*.osr"))
    print(f"{len(files)} replay files in {folder}")
    groups, unknown, failed = defaultdict(list), [], []
    for f in files:
        raw = f.read_bytes()
        try:
            rep = parse_replay(raw, source_path=str(f))
        except Exception as e:  # noqa: BLE001
            failed.append((f.name, f"unreadable: {e}"))
            continue
        cands = by_md5.get(rep.beatmap_md5)
        if not cands:
            unknown.append((f.name, rep.player))
            continue
        # the same map can be listed twice (e.g. The Unforgiving): pick the entry of this player
        ref = next((c for c in cands if c["player"].lower() == (rep.player or "").lower()), cands[0])
        osu = load_osu(rep.beatmap_md5, folder / "maps")
        if osu is None:
            failed.append((f.name, "map download failed"))
            continue
        try:
            a = analyze_bytes(rep, osu, raw)
        except Exception as e:  # noqa: BLE001
            failed.append((f.name, f"analysis failed: {e}"))
            continue
        groups[ref["skill"]].append((ref, a))
    for name, why in failed:
        print(f"  ! {name}: {why}")
    for name, player in unknown:
        print(f"  ? {name} ({player}): not one of the reference maps")
    result = {}
    for skill, items in groups.items():
        key = SKILL_KEY[skill]
        print(f"\n=== {SKILL_LABELS[key]}  ({len(items)} plays)")
        for ref, a in items:
            m = a.meta
            print(f"  {m.get('player'):<12} {ref['title'][:34]:<34} [{ref['version'][:20]}] {m.get('mod_string', '')} "
                  f"{(m.get('accuracy') or 0) * 100:.2f}% {m.get('head_misses')}x miss  {_r(m.get('stars'), 2)}*")
        p = build_profile([a for _, a in items])
        own = p.skills.get(key, {})
        row = {"plays": len(items), "skill": key, "score": _r(own.get("score")),
               "all_scores": {k: _r(v.get("score")) for k, v in p.skills.items()},
               "raw": {k: (_r(v, 3) if isinstance(v, (int, float)) else v) for k, v in own.items()
                       if k not in ("label", "detail") and not isinstance(v, dict)}}
        result[skill] = row
        print(f"  -> {SKILL_LABELS[key]}: {row['score']}   (all skills: {row['all_scores']})")
        print(f"     raw: {row['raw']}")
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    missing = [r for r in refs if r["skill"] not in groups]
    if missing:
        print(f"\nSkills without replays yet: {sorted({r['skill'] for r in missing})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

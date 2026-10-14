"""Validate the judgement simulation against every replay header in dev_data."""
import json
import pathlib
import sys
import time

from osu_coach.beatmaps.domain import PlayableBeatmap
from osu_coach.beatmaps.parser import parse_beatmap_file
from osu_coach.analysis.judge import simulate
from osu_coach.replays.osr import parse_replay_file

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "dev_data")
idx = json.loads((root / "index.json").read_text())
exact = combo_ok = total = 0
rows = []
t0 = time.time()
for e in idx:
    if not e["map_ok"] or e["n300"] + e["n100"] + e["n50"] + e["nmiss"] == 0:
        continue
    r = parse_replay_file(root / "replays" / e["replay"])
    if r.mods & (128 | 8192 | 2048):  # RX / AP / AT
        continue
    pb = PlayableBeatmap(parse_beatmap_file(root / "maps" / f"{e['md5']}.osu"), r.mods)
    s = simulate(pb, r)
    got = (s.counts[300], s.counts[100], s.counts[50], s.counts[0])
    want = (r.n300, r.n100, r.n50, r.nmiss)
    total += 1
    ok = got == want
    exact += ok
    combo_ok += s.max_combo == r.max_combo
    diff = sum(abs(a - b) for a, b in zip(got, want))
    rows.append((diff, e["replay"][:58], r.mod_string, r.version, want, got, r.max_combo, s.max_combo))
print(f"{total} replays, exact counts {exact} ({exact / total:.0%}), combo exact {combo_ok}, {time.time() - t0:.1f}s")
for row in sorted(rows, reverse=True)[:25]:
    if row[0]:
        print(row)

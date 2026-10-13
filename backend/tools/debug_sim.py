"""Debug helper: compare simulation with header and show first problem objects."""
import sys

from osu_coach.domain.beatmap import PlayableBeatmap
from osu_coach.infrastructure.filesystem.beatmap import parse_beatmap_file
from osu_coach.domain.judge import simulate
from osu_coach.infrastructure.filesystem.osr import parse_replay_file

rp, mp = sys.argv[1], sys.argv[2]
replay = parse_replay_file(rp)
pb = PlayableBeatmap(parse_beatmap_file(mp), replay.mods)
sim = simulate(pb, replay)
print("header", replay.n300, replay.n100, replay.n50, replay.nmiss, "combo", replay.max_combo)
print("sim   ", sim.counts[300], sim.counts[100], sim.counts[50], sim.counts[0], "combo", sim.max_combo)
print("windows", sim.hit_windows, "radius", round(sim.radius, 2), "preempt", pb.preempt)
bad = [o for o in sim.objects if o.result in (0, 50, 100)]
for o in bad[: int(sys.argv[3]) if len(sys.argv) > 3 else 12]:
    print(f"#{o.index} {o.kind} t={o.time:.0f} res={o.result} head={o.head_result} err={o.hit_error} reason={o.miss_reason} "
          f"dist={o.miss_dist and round(o.miss_dist,2)} broke={o.broke}/{o.break_reason} ev={o.n_events_hit}/{o.n_events} end={o.end_hit}")
    for c in o.clicks[:6]:
        print(f"      click t={c.time} dist={c.dist:.2f}r action={c.action} in={c.in_range}")

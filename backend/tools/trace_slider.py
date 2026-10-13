"""Debug helper: trace a slider's tracking frame by frame."""
import math
import sys

from osu_coach.domain.beatmap import PlayableBeatmap
from osu_coach.infrastructure.filesystem.beatmap import parse_beatmap_file
from osu_coach.infrastructure.filesystem.osr import parse_replay_file

rp, mp, idx = sys.argv[1], sys.argv[2], int(sys.argv[3])
replay = parse_replay_file(rp)
pb = PlayableBeatmap(parse_beatmap_file(mp), replay.mods)
o = pb.beatmap.objects[idx]
print(o.kind, "t", o.time, "end", o.end_time, "spans", o.spans, "span_dur", round(o.span_duration, 2),
      "len", round(o.pixel_length, 1), "vel", round(o.velocity, 4), "radius", round(pb.radius, 2))
for ev in o.events:
    print("  event", ev.kind, round(ev.time, 2), "prog", round(ev.progress, 3), "pos", [round(v, 1) for v in pb.event_pos(o, ev)])
for t, x, y, k in zip(replay.t, replay.x, replay.y, replay.keys):
    if o.time - 120 <= t <= o.end_time + 40:
        bx, by = pb.pos_at(o, t)
        d = math.hypot(x - bx, y - by)
        print(f"  t={t} cur=({x:.1f},{y:.1f}) keys={k} ball=({bx:.1f},{by:.1f}) d={d:.1f} ({d / pb.radius:.2f}r)")

import type { Schemas } from "../api/client";

type Request = Schemas["PlayGoalRequest"];
type Recommendation = Schemas["GoalRecommendation"];
export const GOAL_MODS: NonNullable<Request["mods"]>[] = ["NM", "HD", "HR", "HDHR", "DT", "HDDT", "HRDT", "HDHRDT"];

export const MOD_PARTS = [
  { value: "EZ", label: "EZ - Easy", blocked: "EZ maps are not in the offline map data yet, so there is nothing to recommend." },
  { value: "HD", label: "HD - Hidden" },
  { value: "HR", label: "HR - Hard Rock" },
  { value: "DT", label: "DT - Double Time 1.5x" },
] as const;

/** Switches one mod on or off in a combination like "HDDT"; EZ and HR exclude each other. With no mods left: NM, or the old value. */
export function toggleMods(current: string, part: string, on: boolean, allowNone = false): NonNullable<Request["mods"]> {
  const set = new Set(current.match(/EZ|HD|HR|DT/g));
  if (on) {
    set.add(part);
    if (part === "EZ") set.delete("HR");
    if (part === "HR") set.delete("EZ");
  } else {
    set.delete(part);
  }
  const next = MOD_PARTS.filter((p) => set.has(p.value)).map((p) => p.value).join("");
  return (next || (allowNone ? "NM" : current)) as NonNullable<Request["mods"]>;
}

type CheckReplay = Schemas["CheckReplay"];

/** One replay per map and mods: the most accurate (then the newest). The ``keep`` path stays listed whatever its rank. */
export function bestReplays(replays: CheckReplay[], keep?: string | null): CheckReplay[] {
  const best = new Map<string, CheckReplay>();
  for (const r of replays) {
    const key = `${r.beatmap_md5 ?? r.path}:${r.mods}`;
    const current = best.get(key);
    const better = !current
      || (r.accuracy ?? -1) > (current.accuracy ?? -1)
      || ((r.accuracy ?? -1) === (current.accuracy ?? -1) && (r.played_at ?? "") > (current.played_at ?? ""));
    if (better) best.set(key, r);
  }
  const picked = new Set([...best.values()].map((r) => r.path));
  return replays.filter((r) => picked.has(r.path) || r.path === keep);
}

export function goalRequest(goal: Request["goal"], remembered?: Request | null): Request {
  return {
    goal,
    replay_path: remembered?.replay_path ?? null,
    beatmap: remembered?.beatmap ?? null,
    mods: remembered?.mods ?? "NM",
    client: "lazer",
    training_mod: remembered?.training_mod ?? "HD",
    farm_mods: remembered?.farm_mods ?? ["NM", "HD", "HR", "DT", "HDDT"],
    online: remembered?.online ?? true,
    min_pp: remembered?.min_pp ?? null,
  };
}

export function exportGoalMaps(recommendations: Recommendation[]): Schemas["MapRow"][] {
  const grouped = new Map<string, Schemas["MapRow"]>();
  for (const recommendation of recommendations) {
    const m = recommendation.map;
    const previous = grouped.get(m.md5);
    if (previous) {
      previous.stage += ` / +${m.mods}`;
      previous.goal += `; ${recommendation.objective}`;
    } else {
      grouped.set(m.md5, {
        md5: m.md5, beatmap_id: m.beatmap_id, beatmapset_id: m.beatmapset_id,
        artist: m.artist, title: m.title, version: m.version,
        stars: null, bpm: null, ar: null, length_s: m.length_s,
        why: recommendation.why, url: `https://osu.ppy.sh/beatmaps/${m.beatmap_id}`,
        stage: `+${m.mods}`, goal: recommendation.objective,
      });
    }
  }
  return [...grouped.values()];
}

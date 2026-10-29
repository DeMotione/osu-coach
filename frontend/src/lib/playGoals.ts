import type { Schemas } from "../api/client";

type Request = Schemas["PlayGoalRequest"];
type Recommendation = Schemas["GoalRecommendation"];
export const GOAL_MODS: NonNullable<Request["mods"]>[] = ["NM", "HD", "HR", "HDHR", "DT", "HDDT", "HRDT", "HDHRDT"];

export function goalRequest(goal: Request["goal"], remembered?: Request | null): Request {
  return {
    goal,
    replay_path: remembered?.replay_path ?? null,
    beatmap: remembered?.beatmap ?? null,
    mods: remembered?.mods ?? "NM",
    client: remembered?.client ?? "stable",
    training_mod: remembered?.training_mod ?? "HD",
    farm_mods: remembered?.farm_mods ?? ["NM", "HD", "HR", "DT", "HDDT"],
    online: remembered?.online ?? true,
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

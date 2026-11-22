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

/** Mods that leave a map's difficulty as it is: a replay with them makes the same goal without them. */
const SAME_DIFFICULTY = new Set(["NM", "NF", "SD", "PF", "SO", "CL", "MU", "V2"]);

/** The speeds DT can be set to in a goal (lazer's custom speeds; the ones the pool's map table holds). */
export const MIN_RATE = 1.1;
export const MAX_RATE = 2;

/** A combination's own speed: DT's (and NC's) 1.5, HT's 0.75, else 1. */
const standardRate = (mods: string) => (/DT|NC/.test(mods) ? 1.5 : /HT|DC/.test(mods) ? 0.75 : 1);

/** A speed a goal can be at with these mods: DT's own (null), or with DT a hundredth from 1.10 to 2.00. */
export function validRate(mods: string, rate: number | null | undefined): boolean {
  if (rate == null) return true;
  const hundredths = rate * 100;
  return mods.includes("DT") && hundredths >= MIN_RATE * 100 - 1e-6 && hundredths <= MAX_RATE * 100 + 1e-6
    && Math.abs(hundredths - Math.round(hundredths)) < 1e-6;
}

/** "+HDDT", "+HDDT ×1.20": the speed when it isn't the combination's own. */
export function modsText(mods: string, rate?: number | null): string {
  const custom = rate != null && Math.abs(rate - standardRate(mods)) > 1e-6;
  return `+${mods}${custom ? ` ×${rate.toFixed(2)}` : ""}`;
}

/** A replay's mods ("HDDT", "DTHD", "NCHD", "HDDTCL", in any order) and speed (default: the mods' own) as the goal
 * combination they make, NC counting as DT, with the speed when it isn't DT's own (else null); undefined when one of
 * them changes the difficulty in a way goals don't cover (EZ, HT, FL, ...) or the speed is not one a goal can be at. */
export function goalMods(replayMods: string, rate?: number | null): { mods: NonNullable<Request["mods"]>; rate: number | null } | undefined {
  const parts = new Set((replayMods.toUpperCase().match(/[A-Z0-9]{2}/g) ?? []).map((m) => (m === "NC" ? "DT" : m)));
  const combo = ["HD", "HR", "DT"].filter((m) => parts.has(m));
  if ([...parts].some((m) => !combo.includes(m) && !SAME_DIFFICULTY.has(m))) return undefined;
  const mods = GOAL_MODS.find((m) => m === (combo.join("") || "NM"));
  if (!mods) return undefined;
  if (rate == null || Math.abs(rate - standardRate(mods)) < 1e-6) return { mods, rate: null };
  return validRate(mods, rate) ? { mods, rate: Math.round(rate * 100) / 100 } : undefined;
}

/** The mods of a replay's label as Detailed Map Analysis shows them ("HDDT", "HDDT ×1.26"), as a goal combination. */
export function goalModsOfLabel(label: string) {
  const [mods, speed] = label.split(" ×");
  return goalMods(mods, speed ? Number(speed) : null);
}

/** Every word of a search in a map's name ("Artist – Title [Version]"), in any case and order: as the API searches. */
export function matchesMap(map: string, search: string): boolean {
  const name = map.toLowerCase();
  return search.toLowerCase().split(/\s+/).every((word) => name.includes(word));
}

export function goalRequest(goal: Request["goal"], remembered?: Request | null): Request {
  return {
    goal,
    replay_path: remembered?.replay_path ?? null,
    beatmap: remembered?.beatmap ?? null,
    mods: remembered?.mods ?? "NM",
    rate: remembered?.rate ?? null,
    client: "lazer",
    training_mod: remembered?.training_mod ?? "HD",
    training_rate: remembered?.training_rate ?? null,
    farm_mods: remembered?.farm_mods ?? ["NM", "HD", "HR", "DT", "HDDT"],
    online: null, // missing maps are downloaded as Settings say
    min_pp: remembered?.min_pp ?? null,
  };
}

export function exportGoalMaps(recommendations: Recommendation[]): Schemas["MapRow"][] {
  const grouped = new Map<string, Schemas["MapRow"]>();
  for (const recommendation of recommendations) {
    const m = recommendation.map;
    const previous = grouped.get(m.md5);
    if (previous) {
      previous.stage += ` / ${modsText(m.mods, m.rate)}`;
      previous.goal += `; ${recommendation.objective}`;
    } else {
      grouped.set(m.md5, {
        md5: m.md5, beatmap_id: m.beatmap_id, beatmapset_id: m.beatmapset_id,
        artist: m.artist, title: m.title, version: m.version,
        stars: null, mods: m.mods, rate: m.rate, bpm: null, ar: null, length_s: m.length_s,
        why: recommendation.why, url: `https://osu.ppy.sh/beatmaps/${m.beatmap_id}`,
        stage: modsText(m.mods, m.rate), goal: recommendation.objective,
      });
    }
  }
  return [...grouped.values()];
}

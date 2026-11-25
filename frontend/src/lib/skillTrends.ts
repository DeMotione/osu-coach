/** The skills' values by period on a real timeline (components/SkillTrends). */
import type { Schemas } from "../api/client";
import { ends, type Period, timeline } from "./progressTime";

type Row = Schemas["PeriodRow"];

export interface Trend {
  key: string;
  label: string;
  points: [number, number | null][];
  last: number | null;
  change: number | null;
}

/** Each skill's values by period on a real timeline (star levels with Star Levels, else 0–100 scores). */
export function skillTrends(rows: Row[], period: Period, skills: { key: string; label: string }[], inStars: boolean): Trend[] {
  const value = (r: Row, key: string) => (inStars ? (r.star_levels?.[key]?.stars ?? null) : (r.skills[key] ?? null));
  return skills
    .map((s) => {
      const points = timeline(rows, period, (r) => value(r, s.key));
      const e = ends(points);
      const values = points.filter((p) => p[1] !== null);
      return { ...s, points, last: values.length ? values[values.length - 1][1] : null, change: e ? e.last - e.first : null };
    })
    .filter((t) => t.points.length > 0);
}

/** A change big enough to call up or down: a tenth of a star, or 2 points of a score. */
export const meaningful = (change: number | null, inStars: boolean) => change !== null && Math.abs(change) >= (inStars ? 0.1 : 2);

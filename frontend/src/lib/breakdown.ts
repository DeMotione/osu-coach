/** The F(m) calculation of a suggested map (``MapRow.breakdown``) as a few readable lines instead of raw JSON (#46). */

import { fmt, isNum, signed, stars } from "./format";

export interface BreakdownLine {
  label: string;
  /** What the term compares, e.g. "5.47★ vs 5.56★". */
  detail: string;
  /** The term's share of F(m). */
  value: string;
}

const obj = (v: unknown): Record<string, unknown> => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
const num = (v: unknown): number | null => (isNum(v) ? v : null);

/** The terms of F(m), one line each; ``[]`` when the breakdown has none. ``label`` names a skill key. */
export function breakdownLines(
  breakdown: Record<string, unknown> | null | undefined,
  mapStars: number | null | undefined,
  skillDemand: number | null | undefined,
  label: (skill: string) => string = (s) => s,
): BreakdownLine[] {
  const b = obj(breakdown);
  const terms = obj(b.terms);
  if (!Object.values(terms).some(isNum)) return [];
  const term = (key: string) => signed(num(terms[key]), 2);
  const over = (Array.isArray(b.bottlenecks) ? b.bottlenecks : [])
    .map(obj)
    .filter((part) => (num(part.overload) ?? 0) > 0)
    .map((part) => `${label(String(part.skill))} +${fmt(num(part.overload), 0)}`);
  return [
    { label: "Stars", detail: `${stars(mapStars)} vs ${stars(num(b.target_stars))}`, value: term("stars") },
    { label: "Skill demand", detail: `${fmt(skillDemand, 0)} vs ${fmt(num(b.reachable_demand), 0)}`, value: term("skill") },
    { label: "Over your level", detail: over.length ? over.join(", ") : "none", value: term("bottlenecks") },
    { label: "History", detail: typeof b.history_source === "string" ? b.history_source.toLowerCase() : "–", value: term("history") },
  ];
}

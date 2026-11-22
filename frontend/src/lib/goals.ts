import type { Schemas } from "../api/client";

type Unit = Schemas["GoalOut"]["unit"];

/** A goal value in its unit: a score as a whole number, stars as the map star rating (Star Levels, #129). */
export function goalValue(v: number | null | undefined, unit: Unit = "score"): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  return unit === "stars" ? `${Number(v.toFixed(2))}★` : v.toFixed(0);
}

/** What is still missing: "12 points" or "0.4★". */
export function goalLeft(v: number, unit: Unit = "score"): string {
  return unit === "stars" ? `${Number(v.toFixed(2))}★` : `${v.toFixed(0)} points`;
}

/** A target a step above ``value``: 10 points (at most 100), or half a star. */
export function nextTarget(value: number, unit: Unit = "score"): number {
  return unit === "stars" ? Math.round((value + 0.5) * 10) / 10 : Math.min(100, Math.round(value) + 10);
}

/** Why a skill can't get a new goal: it has an open one (one per skill; a paused goal doesn't count), or its score
 * can't go any higher. */
export function blockedSkills(goals: Schemas["GoalsOut"]): Map<string, string> {
  const out = new Map<string, string>();
  for (const s of goals.skills) if (s.unit === "score" && s.value >= 100) out.set(s.key, "at 100 already");
  for (const g of goals.open) if (g.state !== "paused") out.set(g.skill, `goal: ${goalValue(g.target, g.unit)} by ${g.deadline}`);
  return out;
}

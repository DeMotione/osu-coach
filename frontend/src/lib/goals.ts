import type { Schemas } from "../api/client";

/** Why a skill can't get a new goal: it has an open one (one per skill; a paused goal doesn't count), or its score
 * can't go any higher. */
export function blockedSkills(goals: Schemas["GoalsOut"]): Map<string, string> {
  const out = new Map<string, string>();
  for (const s of goals.skills) if (s.score >= 100) out.set(s.key, "at 100 already");
  for (const g of goals.open) if (g.state !== "paused") out.set(g.skill, `goal: ${g.target.toFixed(0)} by ${g.deadline}`);
  return out;
}

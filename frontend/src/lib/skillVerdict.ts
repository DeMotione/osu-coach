import type { Schemas } from "../api/client";

type Skill = Schemas["SkillScore"];

/**
 * The strongest and the weakest measured skill, for the Overview's "Work on … first" (#151): every skill with a value
 * on the scale the chart shows. Under Comfort Score that is every skill's 0–100 score, consistency included; under
 * Star Levels the star rating each skill holds up on, which consistency has none of (it isn't on the star scale). A
 * skill only known to be at least something (untested) isn't measured. Null with fewer than two measured skills.
 */
export function bestAndWorst(skills: Skill[], irt: boolean): { best: Skill; worst: Skill; value: (s: Skill) => number } | null {
  const value = (s: Skill) => (irt ? s.stars : s.score) as number;
  const measured = skills.filter((s) => {
    const v = irt ? s.stars : s.score;
    return v !== null && v !== undefined && Number.isFinite(v) && s.state !== "untested";
  });
  if (measured.length < 2) return null;
  const sorted = [...measured].sort((a, b) => value(b) - value(a));
  return { best: sorted[0], worst: sorted[sorted.length - 1], value };
}

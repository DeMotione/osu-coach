/**
 * Comparing the skills with other star ratings. The API counts every skill as a star level (the star rating whose
 * typical maps demand of it what you showed) and, for each star rating offered, the gap to it, the effective level
 * (the weakest skill those maps test most decides) and the chance to pass such a map cleanly.
 */
import type { Schemas } from "../api/client";

type StarCompare = Schemas["StarCompare"];
type CompareTarget = Schemas["CompareTarget"];
type SkillLevel = Schemas["SkillLevel"];

export const COMFORT_HINT = "Your comfort level";

const tenth = (v: number) => Math.round(v * 10) / 10;

/** "7★" for whole stars, "7.5★" otherwise. */
export function starLabel(stars: number): string {
  const v = tenth(stars);
  return Number.isInteger(v) ? `${v}★` : `${v.toFixed(1)}★`;
}

/** A gap in stars with its sign: "+1.2★", "−0.4★", "±0★". */
export function gapLabel(gap: number): string {
  const v = tenth(gap);
  if (v === 0) return "±0★";
  return `${v > 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}★`;
}

/** A skill level, "≥ 13★" when it may be higher, "≤ 1★" when it may be lower. */
export function levelLabel(level: Pick<SkillLevel, "level" | "bound">): string {
  if (level.level === null) return "–";
  const sign = level.bound === "at_least" ? "≥ " : level.bound === "at_most" ? "≤ " : "";
  return `${sign}${starLabel(level.level)}`;
}

/** A pass chance as a rounded percentage: "<1%" and ">99%" at the ends. */
export function chanceLabel(chance: number | null): string {
  if (chance === null) return "–";
  if (chance < 0.005) return "<1%";
  if (chance > 0.995) return ">99%";
  return `${Math.round(chance * 100)}%`;
}

export interface TargetOption {
  value: number;
  label: string;
  disabled: boolean;
  comfort: boolean;
  title?: string;
}

/** The star ratings to pick from, each with its clean-pass chance in the hint. */
export function targetOptions(compare: StarCompare): TargetOption[] {
  return compare.targets.map((t) => {
    const pass = t.pass_chance === null ? "" : `clean pass ${chanceLabel(t.pass_chance)}`;
    return {
      value: t.stars,
      label: starLabel(t.stars),
      disabled: false,
      comfort: t.comfort,
      title: [t.comfort ? COMFORT_HINT : "", pass].filter(Boolean).join(" · ") || undefined,
    };
  });
}

/** The target picked if it is offered, else the one shown first. */
export function pickTarget(compare: StarCompare, picked: number | null): CompareTarget | null {
  const at = (v: number | null) => (v === null ? undefined : compare.targets.find((t) => t.stars === v));
  return at(picked) ?? at(compare.default_target) ?? compare.targets[0] ?? null;
}

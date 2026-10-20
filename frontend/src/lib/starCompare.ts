/**
 * Comparing the comfort-level scores with other star ratings. The API moves every score to each star rating up to
 * `max_gap` stars above the comfort level and to every easier one (lower on harder maps, by how much more their typical
 * maps demand of the skill) with the chance to pass such a map cleanly; the star ratings further above come locked.
 */
import type { Schemas } from "../api/client";

type StarCompare = Schemas["StarCompare"];
type CompareTarget = Schemas["CompareTarget"];

export const COMFORT_HINT = "Your comfort level";

const tenth = (v: number) => Math.round(v * 10) / 10;

/** "7★" for whole stars, "7.5★" otherwise. */
export function starLabel(stars: number): string {
  const v = tenth(stars);
  return Number.isInteger(v) ? `${v}★` : `${v.toFixed(1)}★`;
}

/** A change of score with its sign: "+3", "−14", "±0". */
export function changeLabel(change: number): string {
  const v = Math.round(change);
  return v === 0 ? "±0" : `${v > 0 ? "+" : "−"}${Math.abs(v)}`;
}

/** A pass chance as a rounded percentage: "<1%" and ">99%" at the ends. */
export function chanceLabel(chance: number | null): string {
  if (chance === null) return "–";
  if (chance < 0.005) return "<1%";
  if (chance > 0.995) return ">99%";
  return `${Math.round(chance * 100)}%`;
}

/** Where a star rating lies from the comfort level: "1★ above your comfort level". */
export function fromComfort(stars: number, comfort: number): string {
  const d = tenth(stars - comfort);
  return d === 0 ? "your comfort level" : `${starLabel(Math.abs(d))} ${d > 0 ? "above" : "below"} your comfort level`;
}

export interface TargetOption {
  value: number;
  label: string;
  disabled: boolean;
  comfort: boolean;
  title?: string;
}

/** The star ratings to pick from: the clean-pass chance in the hint, the ones too far away locked. */
export function targetOptions(compare: StarCompare): TargetOption[] {
  return compare.targets.map((t) => {
    const title = t.locked
      ? `Locked: more than ${starLabel(compare.max_gap)} above your comfort level is too big a step to compare yet.`
      : [t.comfort ? COMFORT_HINT : "", t.pass_chance === null ? "" : `clean pass ${chanceLabel(t.pass_chance)}`].filter(Boolean).join(" · ");
    return { value: t.stars, label: starLabel(t.stars), disabled: t.locked, comfort: t.comfort, title: title || undefined };
  });
}

/** The target picked if it is offered and open, else the one shown first. */
export function pickTarget(compare: StarCompare, picked: number | null): CompareTarget | null {
  const at = (v: number | null) => (v === null ? undefined : compare.targets.find((t) => t.stars === v && !t.locked));
  return at(picked) ?? at(compare.default_target) ?? compare.targets.find((t) => !t.locked) ?? null;
}

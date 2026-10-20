/**
 * Readiness of a skill for maps of a target star rating, from the skill's level in stars (the backend's
 * profile/domain/readiness.py). osu! rates a skill as the square root of its strain, so a target asks
 * (target / level)² times the strain the skill handles: it feels that much minus 1 harder, and readiness is
 * 1 minus that, clipped to 0–1 (0 = twice the strain: out of reach).
 */

export const LOCKED_HINT = "Locked. Not enough skill to compare with this level.";
export const COMFORT_HINT = "Your comfort level";

const tenth = (v: number) => Math.round(v * 10) / 10;

export function readiness(level: number | null | undefined, target: number): number | null {
  if (level === null || level === undefined || !Number.isFinite(level) || level <= 0) return null;
  return Math.min(1, Math.max(0, 2 - (target / level) ** 2));
}

/** How much harder the target feels than the skill's level (0.48 = 48% harder; negative = easier). */
export function feltHarder(level: number, target: number): number {
  return (target / level) ** 2 - 1;
}

/** The star rating from which a skill is out of reach (readiness 0). */
export function outOfReachFrom(level: number): number {
  return level * Math.SQRT2;
}

/** "7★" for whole stars, "7.5★" otherwise. */
export function starLabel(stars: number): string {
  const v = tenth(stars);
  return Number.isInteger(v) ? `${v}★` : `${v.toFixed(1)}★`;
}

export interface TargetOption {
  value: number;
  label: string;
  disabled: boolean;
  comfort: boolean;
  title?: string;
}

export interface TargetRange {
  comfort: number;
  ahead: number; // stars above comfort that can be compared with
  step: number; // between the targets near comfort
  min: number;
  max: number;
}

/**
 * The star ratings to compare with: every whole star below the comfort level, the comfort level itself, then
 * `step`s up to `ahead` stars above it; the whole stars beyond that up to `max` are shown locked.
 */
export function targetOptions({ comfort, ahead, step, min, max }: TargetRange): TargetOption[] {
  const base = Math.min(tenth(comfort), max);
  const top = Math.min(base + ahead, max);
  const option = (value: number, disabled = false): TargetOption => ({
    value,
    label: starLabel(value),
    disabled,
    comfort: value === base,
    title: disabled ? LOCKED_HINT : value === base ? COMFORT_HINT : undefined,
  });
  const out: TargetOption[] = [];
  for (let s = Math.ceil(min); s <= base - step + 1e-9; s++) out.push(option(s));
  for (let v = base; v <= top + 1e-9; v = tenth(v + step)) out.push(option(v));
  for (let s = Math.floor(top) + 1; s <= max; s++) out.push(option(s, true));
  return out;
}

/** The target shown first: one star above the comfort level (or the highest one open). */
export function defaultTarget({ comfort, ahead, max }: Pick<TargetRange, "comfort" | "ahead" | "max">): number {
  const base = Math.min(tenth(comfort), max);
  return tenth(Math.min(base + Math.min(1, ahead), max));
}

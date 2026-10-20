/**
 * Readiness of a skill for maps of a target star rating, from the skill's level in stars (the backend's
 * profile/domain/readiness.py). osu! rates a skill as the square root of its strain, so a target asks
 * (target / level)² times the strain the skill handles: it feels that much minus 1 harder, and readiness is
 * 1 minus that, clipped to 0–1 (0 = twice the strain: out of reach).
 */

export const LOCKED_HINT = "Locked. Not enough skill to compare with this level.";
const LOCKED_STEPS = 2; // locked targets shown past the last open one

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

export interface TargetOption {
  value: number;
  label: string;
  disabled: boolean;
  title?: string;
}

/** Targets above the comfort level in `step`s: open up to `ahead` stars above it, the next few locked. */
export function targetOptions(comfort: number, ahead: number, step: number): TargetOption[] {
  const base = tenth(comfort);
  const open = Math.round(ahead / step);
  return Array.from({ length: open + LOCKED_STEPS }, (_, i) => {
    const value = tenth(base + (i + 1) * step);
    const disabled = i >= open;
    return { value, label: `${value.toFixed(1)}★`, disabled, title: disabled ? LOCKED_HINT : undefined };
  });
}

/** The target shown first: one star above the comfort level (or the furthest open one if that is closer). */
export function defaultTarget(comfort: number, ahead: number): number {
  return tenth(tenth(comfort) + Math.min(1, ahead));
}

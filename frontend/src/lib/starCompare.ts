/**
 * Comparing the comfort-level skill scores with other star ratings. A map of ``target`` stars feels
 * ``(target / comfort)² − 1`` harder than the comfort level (osu! rates a skill as the square root of its strain, so
 * strain grows with the square of the star rating): +1★ for a 5★ player feels 44% harder, +2★ 96%.
 *
 * * harder: the score loses that share, so it reaches 0 (out of reach) at comfort × √2 — twice the strain;
 * * easier: the gap to 100 shrinks by the same ratio, so scores rise towards 100 on easy maps.
 */

export const LOCKED_HINT = "Locked. Not enough skill to compare with this level.";
export const COMFORT_HINT = "Your comfort level";

const tenth = (v: number) => Math.round(v * 10) / 10;

/** How much harder the target feels than the comfort level (0.33 = 33% harder; negative = easier). */
export function feltHarder(comfort: number, target: number): number {
  return (target / comfort) ** 2 - 1;
}

/** A comfort-level score (0–100) moved to another star rating. */
export function scoreAt(score: number | null | undefined, comfort: number, target: number): number | null {
  if (score === null || score === undefined || !Number.isFinite(score) || !(comfort > 0)) return null;
  const ratio = (target / comfort) ** 2;
  return ratio >= 1 ? score * Math.max(0, 2 - ratio) : 100 - (100 - score) * ratio;
}

/** From this star rating every skill is out of reach (twice the strain of the comfort level). */
export function outOfReachFrom(comfort: number): number {
  return comfort * Math.SQRT2;
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

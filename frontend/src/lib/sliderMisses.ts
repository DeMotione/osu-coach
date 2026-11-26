/**
 * Slider misses by length and speed (the Sliders & Reading page): the counts of the speeds picked, added up per
 * length, and which lengths and speeds are clearly worse. They are counts of whole sliders, so the test is the exact
 * one: 6 of 16 missed says a lot, 1 of 16 doesn't, and neither depends on having 40 of them.
 */
import type { Schemas } from "../api/client";
import { type Judged, MIN_NOTES, type Standing } from "./verdict";

type Misses = Schemas["SliderMisses"];

export interface Step {
  /** whole circle widths (length) or circle widths per second (speed) */
  step: number;
  n: number;
  head: number;
  broke: number;
}

export const missed = (s: Pick<Step, "head" | "broke">) => s.head + s.broke;

const sum = (steps: Step[], step = 0): Step =>
  steps.reduce((a, s) => ({ step, n: a.n + s.n, head: a.head + s.head, broke: a.broke + s.broke }), { step, n: 0, head: 0, broke: 0 });

/** All the sliders of the speeds picked (none picked: every speed). */
export const total = (m: Misses, speeds: number[]): Step =>
  sum(m.cells.filter((c) => !speeds.length || speeds.includes(c.speed)).map((c) => ({ step: 0, n: c.n, head: c.head, broke: c.broke })));

const steps = (top: number) => Array.from({ length: top + 1 }, (_, i) => i);

/** Per length, 0–1 to ``length_top`` and longer, for the speeds picked (none picked: every speed). */
export const byLength = (m: Misses, speeds: number[]): Step[] =>
  steps(m.length_top).map((length) => ({ ...total({ ...m, cells: m.cells.filter((c) => c.length === length) }, speeds), step: length }));

/** Per speed, 0 to ``speed_top`` and faster, over every length. */
export const bySpeed = (m: Misses): Step[] =>
  steps(m.speed_top).map((speed) => ({ ...sum(m.cells.filter((c) => c.speed === speed).map((c) => ({ ...c, step: speed }))), step: speed }));

/** Chance of at most ``k`` misses in ``n`` sliders each missed with probability ``p`` (the binomial distribution; the
 * normal one when so many are expected that they agree). */
export function atMost(k: number, n: number, p: number): number {
  if (k < 0) return 0;
  if (k >= n) return 1;
  if (p <= 0) return 1;
  if (p >= 1) return 0;
  const expected = n * p;
  if (expected > 200) {
    const z = (k + 0.5 - expected) / Math.sqrt(expected * (1 - p));
    // the error function, to about 1e-7 (Abramowitz & Stegun 7.1.26)
    const x = Math.abs(z) / Math.SQRT2;
    const t = 1 / (1 + 0.3275911 * x);
    const tail = 0.5 * t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429)))) * Math.exp(-x * x);
    return z < 0 ? tail : 1 - tail;
  }
  let term = Math.exp(n * Math.log1p(-p));
  let chance = term;
  for (let i = 1; i <= k; i++) {
    term *= ((n - i + 1) / i) * (p / (1 - p));
    chance += term;
  }
  return Math.min(1, chance);
}

const SURE = 0.01; // the chance of a count this far off if it were your average, to call it worse / better
const WORSE = 1.5;
const BETTER = 0.67;
const FEWEST = 10; // under this many sliders nothing is called

/** Is this many misses clearly more or less than ``average`` (0–1)? */
export function standing(s: Step, average: number | null): Standing {
  if (!s.n || average === null || s.n < FEWEST) return "few";
  const rate = missed(s) / s.n;
  if (rate >= average * WORSE && 1 - atMost(missed(s) - 1, s.n, average) < SURE) return "worse";
  if (rate <= average * BETTER && atMost(missed(s), s.n, average) < SURE) return "better";
  return s.n < MIN_NOTES ? "few" : "usual";
}

export type JudgedStep = Judged & Step;

/** Steps against your average over all your sliders, whichever speeds are picked. */
export function judgeSteps(list: Step[], average: number | null, label: (step: number) => string): JudgedStep[] {
  return list.map((s) => {
    const rate = s.n ? missed(s) / s.n : null;
    return { ...s, label: label(s.step), rate, standing: standing(s, average), usual: average, ratio: rate !== null && average ? rate / average : null };
  });
}

/** "2–3" circle widths long; "8+" for the last step. */
export const lengthLabel = (top: number) => (step: number) => (step >= top ? `${top}+` : `${step}–${step + 1}`);
/** The speed as its button says it; "16+" for the last step. */
export const speedLabel = (top: number) => (step: number) => (step >= top ? `${top}+` : String(step));

export interface Stretch extends Step {
  from: number;
  to: number;
}

/** Clearly worse steps next to each other taken together (5–6, 6–7 and 7–8 → 5 to 8), the one costing the most misses
 * over your average first. */
export function worseStretches(judged: JudgedStep[], average: number | null): Stretch[] {
  const out: Stretch[] = [];
  for (const s of judged) {
    if (s.standing !== "worse") continue;
    const last = out[out.length - 1];
    if (last && last.to === s.step - 1) Object.assign(last, sum([last, s]), { to: s.step });
    else out.push({ step: s.step, n: s.n, head: s.head, broke: s.broke, from: s.step, to: s.step });
  }
  const excess = (s: Step) => missed(s) - s.n * (average ?? 0);
  return out.sort((a, b) => excess(b) - excess(a));
}

/** "5 circle widths or longer", "5 to 8 circle widths long". */
export const lengthWords = (from: number, to: number, top: number) =>
  to >= top ? `${from} circle widths or longer` : `${from} to ${to + 1} circle widths long`;

/** Speeds in order, neighbours together: "speed 13", "speeds 4 and 13–15", "speeds 13 and up". */
export function speedWords(speeds: number[], top: number): string {
  const runs: [number, number][] = [];
  for (const s of [...speeds].sort((a, b) => a - b)) {
    const last = runs[runs.length - 1];
    if (last && last[1] === s - 1) last[1] = s;
    else runs.push([s, s]);
  }
  const words = runs.map(([a, b]) => (b >= top ? `${a} and up` : a === b ? String(a) : `${a}–${b}`));
  const list = words.length > 1 ? `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}` : (words[0] ?? "");
  return `speed${speeds.length > 1 || runs.some(([, b]) => b >= top) ? "s" : ""} ${list}`;
}

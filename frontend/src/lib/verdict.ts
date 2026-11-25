/**
 * Which bars of a chart say something: each group of notes (a jump direction, a slider length, an AR) against your
 * average miss rate, with a test that its difference isn't chance. A chart then colours what is clearly worse or
 * better and greys out what rests on too few notes, and its card can say the answer in a sentence.
 */

/** A group of notes: how many (difficulty-weighted counts are fine) and the share of them missed (0–1). */
export interface Group {
  label: string;
  rate: number | null;
  n: number;
}

export type Standing = "worse" | "usual" | "better" | "few";

export interface Judged extends Group {
  standing: Standing;
  /** your average miss rate over all the groups (see {@link usualRate}) and how many times it this group's is */
  usual: number | null;
  ratio: number | null;
}

/** Fewer notes than this: the share could be anything, the bar is greyed out. */
export const MIN_NOTES = 40;
/** How sure (in standard errors) a difference has to be, and how big, to be called worse / better. */
const Z = 2;
const WORSE = 1.5;
const BETTER = 0.67;

/** The share of all the groups' notes missed (null without notes). */
export function overall(groups: Group[]): number | null {
  let misses = 0;
  let n = 0;
  for (const g of groups) {
    if (g.rate === null || !(g.n > 0)) continue;
    misses += g.rate * g.n;
    n += g.n;
  }
  return n > 0 ? misses / n : null;
}

/** Your average miss rate over these groups: all their notes together (what a player compares with). */
export const usualRate = (groups: Group[]): number | null => overall(groups);

/** Each group against your average: worse / usual / better, or too few notes to tell. */
export function judge(groups: Group[], minNotes = MIN_NOTES): Judged[] {
  const usual = usualRate(groups);
  return groups.map((g) => {
    if (g.rate === null || !(g.n > 0)) return { ...g, standing: "few", usual, ratio: null };
    const ratio = usual !== null && usual > 0 ? g.rate / usual : null;
    if (g.n < minNotes || usual === null) return { ...g, standing: "few", usual, ratio };
    const se = Math.sqrt(Math.max(usual * (1 - usual), 1e-6) / g.n);
    const z = (g.rate - usual) / se;
    const standing: Standing =
      z >= Z && g.rate >= usual * WORSE ? "worse" : z <= -Z && g.rate <= usual * BETTER ? "better" : "usual";
    return { ...g, standing, usual, ratio };
  });
}

/** The clearly worse groups, the biggest excess of misses first (many notes a bit worse can matter more than a few
 * much worse). */
export function weakest(judged: Judged[]): Judged[] {
  return judged
    .filter((g) => g.standing === "worse")
    .sort((a, b) => (b.rate! - (b.usual ?? 0)) * b.n - (a.rate! - (a.usual ?? 0)) * a.n);
}

/** "4.1%" for a 0–1 share; one decimal under 10%, none above. */
export function share(rate: number | null | undefined): string {
  if (rate === null || rate === undefined || !Number.isFinite(rate)) return "–";
  const p = rate * 100;
  return `${p < 10 ? p.toFixed(1) : p.toFixed(0)}%`;
}

/** "2.1×" how many times the rest; "–" without one. */
export const times = (ratio: number | null | undefined): string =>
  ratio === null || ratio === undefined || !Number.isFinite(ratio) ? "–" : `${ratio.toFixed(1)}×`;

/** Labels joined as people write them: "a", "a and b", "a, b and c". */
export function listed(labels: string[]): string {
  if (labels.length <= 1) return labels[0] ?? "";
  return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
}

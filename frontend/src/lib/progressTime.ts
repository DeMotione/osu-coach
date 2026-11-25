/**
 * Progress periods on a real timeline: a month, an ISO week or a day by its key, and the gaps between periods with
 * plays, so a chart puts 2021-09 and 2024-11 three years apart and doesn't draw a line through the years between.
 */

export type Period = "month" | "week" | "day";

const DAY_MS = 86_400_000;
const LENGTH_DAYS: Record<Period, number> = { month: 31, week: 7, day: 1 };

/** When a period starts (local midnight): "2026-11" → 1 Nov 2026, "2026-W47" → Monday of ISO week 47, "2026-11-18". */
export function periodStart(key: string): Date | null {
  let m = /^(\d{4})-(\d{2})$/.exec(key);
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, 1);
  m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(key);
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  m = /^(\d{4})-W(\d{2})$/.exec(key);
  if (m) {
    // ISO week 1 is the week with 4 January in it; weeks start on Monday
    const jan4 = new Date(Number(m[1]), 0, 4);
    const monday = new Date(jan4.getFullYear(), 0, 4 - ((jan4.getDay() + 6) % 7));
    return new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + (Number(m[2]) - 1) * 7);
  }
  return null;
}

/** Points [time, value] of the periods with a value, with a break (a null) where periods without plays lie between
 * two of them: a line chart doesn't join across the gap. */
export function timeline<R extends { key: string }>(rows: R[], period: Period, value: (r: R) => number | null | undefined): [number, number | null][] {
  const out: [number, number | null][] = [];
  let last: number | null = null;
  for (const r of rows) {
    const v = value(r);
    const start = periodStart(r.key);
    if (v === null || v === undefined || !Number.isFinite(v) || !start) continue;
    const t = start.getTime();
    if (last !== null && t - last > LENGTH_DAYS[period] * 1.5 * DAY_MS) out.push([(last + t) / 2, null]);
    out.push([t, v]);
    last = t;
  }
  return out;
}

/** The first and the last value of a timeline (to tell the change between them). */
export function ends(points: [number, number | null][]): { first: number; last: number } | null {
  const values = points.filter((p): p is [number, number] => p[1] !== null);
  return values.length >= 2 ? { first: values[0][1], last: values[values.length - 1][1] } : null;
}

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** A period as people say it: "Oct 2026", "the week of 29 Sep", "29 Sep". */
export function periodLabel(key: string): string {
  const d = periodStart(key);
  if (!d) return key;
  if (/^\d{4}-\d{2}$/.test(key)) return `${MONTH_NAMES[d.getMonth()]} ${d.getFullYear()}`;
  const day = `${d.getDate()} ${MONTH_NAMES[d.getMonth()]}`;
  return key.includes("W") ? `the week of ${day}` : day;
}

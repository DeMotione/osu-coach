import { isoDay } from "./format";

/** A day on this computer's calendar, YYYY-MM-DD: compares in the right order as text. */
export type Day = string;

/** A range of days, both included; ``to`` is null while only the first day is picked. */
export interface DayRange {
  from: Day;
  to: Day | null;
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
  "November", "December"];

/** The calendar's column headers, Monday first. */
export const WEEK = [...WEEKDAYS.slice(1), WEEKDAYS[0]];

const toDate = (day: Day) => {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d);
};

/** The day of an ISO time (UTC) on this computer's calendar. */
export const dayOf = (iso: string): Day => isoDay(0, new Date(iso));

/** "Wed, 08 Jun" */
export function dayLabel(day: Day): string {
  const d = toDate(day);
  return `${WEEKDAYS[d.getDay()]}, ${String(d.getDate()).padStart(2, "0")} ${MONTHS[d.getMonth()]}`;
}

/** "08 Jun 2026 – 23 Jun 2026", one day on its own when it starts and ends the range. */
export function rangeLabel(r: DayRange): string {
  const one = (day: Day) => {
    const d = toDate(day);
    return `${String(d.getDate()).padStart(2, "0")} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  };
  return !r.to || r.to === r.from ? one(r.from) : `${one(r.from)} – ${one(r.to)}`;
}

/** "June, 2022" for a month (0-based ``month``). */
export const monthLabel = (year: number, month: number) => `${MONTH_NAMES[month]}, ${year}`;

/** The month ``by`` months after (before, when negative) the one given: [year, 0-based month]. */
export function shiftMonth(year: number, month: number, by: number): [number, number] {
  const d = new Date(year, month + by, 1);
  return [d.getFullYear(), d.getMonth()];
}

/** The six weeks a month is shown in, Monday first: the days around it fill the first and last week. */
export function monthGrid(year: number, month: number): Day[] {
  const first = new Date(year, month, 1);
  const start = new Date(year, month, 1 - ((first.getDay() + 6) % 7));
  return Array.from({ length: 42 }, (_, i) => isoDay(i, start));
}

/** The month (as [year, 0-based month]) a day is in. */
export function monthOf(day: Day): [number, number] {
  const d = toDate(day);
  return [d.getFullYear(), d.getMonth()];
}

/** A click on ``day``: the first click picks the first day, the next one the last (the two are swapped when it is
 * earlier); a click once both are picked starts a new range. */
export function pickDay(r: DayRange | null, day: Day): DayRange {
  if (!r || r.to) return { from: day, to: null };
  return day < r.from ? { from: day, to: r.from } : { from: r.from, to: day };
}

/** The range as the API takes it: from the start of the first day up to (not including) the start of the day after
 * the last, both on this computer's clock, in UTC. */
export function utcRange(r: DayRange): { since: string; until: string } {
  const to = toDate(r.to ?? r.from);
  return { since: toDate(r.from).toISOString(), until: new Date(to.getFullYear(), to.getMonth(), to.getDate() + 1).toISOString() };
}

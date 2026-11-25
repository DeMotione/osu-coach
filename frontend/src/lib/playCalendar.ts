/** The play calendar's numbers (components/PlayCalendar). */
import { isoDay } from "./format";

/** How busy a day was: 0 = no plays, then 1–2, 3–5, 6–9, 10+. */
export const playLevel = (plays: number) => (plays <= 0 ? 0 : plays <= 2 ? 1 : plays <= 5 ? 2 : plays <= 9 ? 3 : 4);

/** Days played in the last ``days`` days (up to today), the longest run of days without a play between two played
 * days of the last year, and the days since the last play. */
export function playStats(plays: Map<string, number>, today = new Date()) {
  const played = (back: number) => plays.get(isoDay(-back, today)) ?? 0;
  let lastYear = 0;
  let lastMonth = 0;
  let longestBreak = 0;
  let gap = 0;
  let seen = false;
  let since: number | null = null;
  for (let back = 364; back >= 0; back--) {
    if (played(back) > 0) {
      lastYear++;
      if (back < 30) lastMonth++;
      if (seen) longestBreak = Math.max(longestBreak, gap);
      seen = true;
      gap = 0;
      since = back;
    } else if (seen) gap++;
  }
  return { lastYear, lastMonth, longestBreak, daysSince: since };
}

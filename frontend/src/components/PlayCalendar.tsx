import { useMemo } from "react";

import { isoDay } from "../lib/format";
import { playLevel } from "../lib/playCalendar";

const WEEKS = 53;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * The last year as a calendar, a column per week (Monday on top) and a square per day, the darker the more you played
 * that day: when you play, how often, and the breaks, at a glance.
 */
export function PlayCalendar({ plays, today = new Date() }: { plays: Map<string, number>; today?: Date }) {
  const weeks = useMemo(() => {
    // the Monday of the week WEEKS-1 weeks before this one
    const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - ((today.getDay() + 6) % 7) - (WEEKS - 1) * 7);
    const end = isoDay(0, today);
    return Array.from({ length: WEEKS }, (_, w) =>
      Array.from({ length: 7 }, (_, d) => {
        const day = isoDay(w * 7 + d, monday);
        return day > end ? null : { day, plays: plays.get(day) ?? 0 };
      }),
    );
  }, [plays, today]);
  return (
    <div className="play-calendar" role="img" aria-label="Days you played in the last year">
      <div className="play-calendar__months" aria-hidden="true">
        {weeks.map((w, i) => {
          const first = w.find((c) => c && c.day.endsWith("-01"));
          return <span key={i}>{first ? MONTHS[Number(first.day.slice(5, 7)) - 1] : ""}</span>;
        })}
      </div>
      <div className="play-calendar__days">
        {weeks.map((w, i) => (
          <div key={i} className="play-calendar__week">
            {w.map((c, d) =>
              c ? (
                <span key={d} className={`play-calendar__day play-calendar__day--${playLevel(c.plays)}`} title={`${c.day}: ${c.plays} ${c.plays === 1 ? "play" : "plays"}`} />
              ) : (
                <span key={d} className="play-calendar__day play-calendar__day--future" />
              ),
            )}
          </div>
        ))}
      </div>
      <div className="play-calendar__key" aria-hidden="true">
        less
        {[0, 1, 2, 3, 4].map((l) => (
          <span key={l} className={`play-calendar__day play-calendar__day--${l}`} />
        ))}
        more
      </div>
    </div>
  );
}

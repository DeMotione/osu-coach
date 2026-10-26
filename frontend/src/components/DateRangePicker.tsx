import { useEffect, useRef, useState } from "react";

import {
  dayLabel,
  monthGrid,
  monthLabel,
  monthOf,
  pickDay,
  rangeLabel,
  shiftMonth,
  WEEK,
  type Day,
  type DayRange,
} from "../lib/dateRange";
import { isoDay } from "../lib/format";
import { IconCalendar, IconChevronLeft, IconChevronRight, IconX } from "./icons";

/** A button naming the days chosen ("All dates" when none) that opens a calendar to pick the first and the last
 * day. Only the days in ``played`` (the days with plays) can be picked; the calendar starts with the last of them. */
export function DateRangePicker({ value, onChange, played, label = "Dates" }: {
  value: DayRange | null;
  onChange: (range: DayRange | null) => void;
  played: Set<Day>;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="date-range">
      <button type="button" className="btn btn--sm date-range__button" aria-label={`${label}: ${value ? rangeLabel(value) : "all dates"}`}
        disabled={!played.size} onClick={() => setOpen(true)}>
        <IconCalendar /> <span>{value ? rangeLabel(value) : "All dates"}</span>
      </button>
      {value && (
        <button type="button" className="btn btn--ghost btn--sm btn--icon" aria-label="All dates" title="All dates"
          onClick={() => onChange(null)}>
          <IconX />
        </button>
      )}
      {open && (
        <CalendarDialog value={value} played={played} onClose={() => setOpen(false)}
          onApply={(r) => { onChange(r); setOpen(false); }} />
      )}
    </div>
  );
}

function CalendarDialog({ value, played, onApply, onClose }: {
  value: DayRange | null;
  played: Set<Day>;
  onApply: (range: DayRange) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const sorted = [...played].sort();
  const [first, last] = [sorted[0] ?? isoDay(), sorted.at(-1) ?? isoDay()];
  // nothing picked yet: from the last day with plays, so one more click picks how far back to go
  const [range, setRange] = useState<DayRange | null>(value ?? (sorted.length ? { from: last, to: null } : null));
  const [hover, setHover] = useState<Day | null>(null);
  const [[year, month], setMonth] = useState<[number, number]>(monthOf(value?.to ?? value?.from ?? last));
  // the months with plays, as YYYY-MM to compare
  const at = (y: number, m: number) => `${y}-${String(m + 1).padStart(2, "0")}`;
  const [earlier, later] = [at(year, month) > first.slice(0, 7), at(year, month) < last.slice(0, 7)];

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (typeof d.showModal === "function") d.showModal();
    else d.setAttribute("open", "");
    return () => d.close?.();
  }, []);

  // while only the first day is picked, the range runs to the day under the pointer
  const end = range?.to ?? (range && hover ? hover : null);
  const [lo, hi] = range && end ? (end < range.from ? [end, range.from] : [range.from, end]) : [range?.from, range?.from];
  const days = monthGrid(year, month);
  const inMonth = (day: Day) => monthOf(day)[1] === month;

  return (
    <dialog ref={ref} className="calendar" aria-label="Pick the first and the last day" onClose={onClose}
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="calendar__ends">
        <div>
          <span>From</span>
          <strong>{range ? dayLabel(range.from) : "–"}</strong>
        </div>
        <div>
          <span>To</span>
          <strong>{range?.to ? dayLabel(range.to) : "–"}</strong>
        </div>
      </div>
      <div className="calendar__month">
        <button type="button" className="calendar__step" aria-label="Previous month" disabled={!earlier}
          onClick={() => setMonth(shiftMonth(year, month, -1))}>
          <IconChevronLeft />
        </button>
        <span aria-live="polite">{monthLabel(year, month)}</span>
        <button type="button" className="calendar__step" aria-label="Next month" disabled={!later}
          onClick={() => setMonth(shiftMonth(year, month, 1))}>
          <IconChevronRight />
        </button>
      </div>
      <div className="calendar__grid" onPointerLeave={() => setHover(null)}>
        {WEEK.map((w) => (
          <span key={w} className="calendar__weekday">{w}</span>
        ))}
        {days.map((day) => {
          const ends = day === lo || day === hi;
          const cls = [
            "calendar__day",
            inMonth(day) ? "" : "is-outside",
            lo && hi && lo !== hi && day >= lo && day <= hi ? "is-in" : "",
            lo !== hi && day === lo ? "is-first" : "",
            lo !== hi && day === hi ? "is-last" : "",
            ends ? "is-end" : "",
            played.has(day) ? "has-plays" : "",
          ].filter(Boolean).join(" ");
          return (
            <button key={day} type="button" className={cls} disabled={!played.has(day)}
              aria-label={`${dayLabel(day)}${played.has(day) ? "" : ", no plays"}`} aria-pressed={day === range?.from || day === range?.to}
              onPointerEnter={() => setHover(day)} onClick={() => setRange(pickDay(range, day))}>
              <span>{Number(day.slice(8))}</span>
            </button>
          );
        })}
      </div>
      <div className="calendar__foot">
        <button type="button" className="btn calendar__action" onClick={onClose}>Cancel</button>
        <button type="button" className="btn btn--primary calendar__action" disabled={!range}
          onClick={() => range && onApply({ from: range.from, to: range.to ?? range.from })}>
          Apply
        </button>
      </div>
    </dialog>
  );
}

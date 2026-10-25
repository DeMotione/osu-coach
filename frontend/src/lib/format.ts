/** Number and time formatting. Every formatter shows "–" for missing values (null / NaN). */

export const NONE = "–";

export function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

const grouped = (v: number, digits: number) =>
  v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** A number with ``digits`` decimals (thousands grouped), and an optional suffix. */
export function fmt(v: number | null | undefined, digits = 1, suffix = ""): string {
  return isNum(v) ? grouped(v, digits) + suffix : NONE;
}

/** A whole number with thousands grouped. */
export function int(v: number | null | undefined): string {
  return isNum(v) ? grouped(Math.round(v), 0) : NONE;
}

/** A fraction (0–1) as a percentage. */
export function pct(v: number | null | undefined, digits = 1): string {
  return isNum(v) ? `${(v * 100).toFixed(digits)}%` : NONE;
}

/** With an explicit sign: "+1.2", "−0.4" (a real minus sign). */
export function signed(v: number | null | undefined, digits = 1, suffix = ""): string {
  if (!isNum(v)) return NONE;
  const s = Math.abs(v).toFixed(digits);
  const zero = Number(s) === 0;
  return `${zero ? "±" : v > 0 ? "+" : "−"}${s}${suffix}`;
}

export function stars(v: number | null | undefined, digits = 2): string {
  return isNum(v) ? `${v.toFixed(digits)}★` : NONE;
}

/** Seconds as m:ss. */
export function clock(seconds: number | null | undefined): string {
  if (!isNum(seconds)) return NONE;
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** A duration as the profile names its windows: "10 s", "2 min". */
export function span(seconds: number): string {
  return seconds < 60 ? `${Math.round(seconds)} s` : `${Math.round(seconds / 60)} min`;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** An ISO time (UTC) on this computer's clock: "2026-09-13 22:16". */
export function localTime(iso: string | null | undefined): string {
  if (!iso) return NONE;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return NONE;
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Today (or ``days`` from today) as YYYY-MM-DD on this computer's calendar. */
export function isoDay(days = 0, from: Date = new Date()): string {
  const d = new Date(from.getFullYear(), from.getMonth(), from.getDate() + days);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** The short name of a skill label: "Flow aim (spaced streams)" → "Flow aim". */
export function shortLabel(label: string): string {
  return label.split(" (")[0];
}

/** "Artist – Title [Version]" */
export function mapName(m: { artist: string; title: string; version: string }): string {
  return `${m.artist} – ${m.title} [${m.version}]`;
}

/** Escape text for the HTML of chart tooltips. */
export function esc(text: string | number): string {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

/** The Tapping page's verdicts: what its numbers say, in a sentence each. */
import type { Schemas } from "../api/client";
import { MIN_NOTES } from "./verdict";

export type Tone = "bad" | "good" | "info" | "muted";
export interface Said {
  tone: Tone;
  text: string;
}

/** Hit timing: centred, or early / late by how much (a few ms either way is noise in a replay). */
export function timingVerdict(mean: number | null): Said | null {
  if (mean === null || !Number.isFinite(mean)) return null;
  const ms = Math.abs(mean).toFixed(1);
  if (Math.abs(mean) < 3) return { tone: "good", text: `Your timing is centred: on average ${ms} ms ${mean < 0 ? "early" : "late"}, which is nothing to fix.` };
  const way = mean < 0 ? "early" : "late";
  if (Math.abs(mean) < 8)
    return { tone: "info", text: `You tap a little ${way}: ${ms} ms on average. Fine, but watch it on high OD maps.` };
  return {
    tone: "bad",
    text: `You tap ${way}: ${ms} ms on average, every play. That costs 300s — check your audio offset, then practise timing on easy maps.`,
  };
}

const LEFT = new Set(["K1", "M1", "L"]);
const RIGHT = new Set(["K2", "M2", "R"]);
/** Chatter below this (per 1000 presses) is normal bounce. */
const CHATTER = 5;

/** Keys: chatter first (a hardware problem), then one finger doing most presses (the left keys K1 / M1 / L against the
 * right ones K2 / M2 / R: osu!stable and lazer name them differently), then streams not alternated. */
export function keysVerdict(keys: Schemas["KeyUsage"], alternation: number | null): Said | null {
  if (!keys.shares.length) return null;
  if (keys.chatter_per_1000 !== null && keys.chatter_per_1000 >= CHATTER)
    return {
      tone: "bad",
      text: `Your keys double-press: ${keys.chatter_per_1000.toFixed(1)} presses per 1000 come a few ms after the one before. Check the switch or raise the rapid-trigger / debounce setting.`,
    };
  const left = keys.shares.filter((s) => LEFT.has(s.key)).reduce((sum, s) => sum + s.share, 0);
  const right = keys.shares.filter((s) => RIGHT.has(s.key)).reduce((sum, s) => sum + s.share, 0);
  const both = left + right;
  if (both > 0) {
    const lean = Math.max(left, right) / both;
    if (lean >= 0.65)
      return {
        tone: "bad",
        text: `You lean on one finger: your ${left > right ? "left" : "right"} key takes ${Math.round(lean * 100)}% of the presses. Alternate more in streams and bursts.`,
      };
  }
  if (alternation !== null && alternation < 0.8)
    return {
      tone: "bad",
      text: `You alternate ${Math.round(alternation * 100)}% of stream notes: the rest you tap twice with one finger, which tires it out. Practise alternating from the first note.`,
    };
  return {
    tone: "good",
    text: both > 0
      ? `You use both fingers evenly: left ${Math.round((left / both) * 100)}% · right ${Math.round((right / both) * 100)}%${alternation !== null ? `, ${Math.round(alternation * 100)}% of stream notes alternated` : ""}.`
      : "Your keys look fine.",
  };
}

/** Do streams fall apart later in a map? The miss rate of the last third of the map against the first, if both rest
 * on enough notes and it is clearly higher. */
export function lateInMap(s: Schemas["StreamsOverTime"] | null): string | null {
  const overall = s?.map.lines.find((l) => l.key === "overall");
  if (!overall || overall.points.length < 3) return null;
  const third = Math.max(1, Math.floor(overall.points.length / 3));
  const rate = (pts: Schemas["StreamPoint"][]) => {
    const n = pts.reduce((sum, p) => sum + (p.miss_rate === null ? 0 : p.n), 0);
    const missed = pts.reduce((sum, p) => sum + (p.miss_rate === null ? 0 : (p.miss_rate / 100) * p.n), 0);
    return { n, rate: n ? missed / n : null };
  };
  const early = rate(overall.points.slice(0, third));
  const late = rate(overall.points.slice(-third));
  if (early.rate === null || late.rate === null || early.n < MIN_NOTES || late.n < MIN_NOTES) return null;
  if (late.rate >= Math.max(early.rate * 1.5, early.rate + 0.01))
    return `Late in maps your streams fall apart more: ${(late.rate * 100).toFixed(1)}% of stream notes missed in the last third, ${(early.rate * 100).toFixed(1)}% in the first.`;
  return null;
}

/** Stream speeds as "150–159" ranges, joined. */
export const bpmRanges = (bpms: number[]) => bpms.map((b) => `${b}–${b + 9}`);

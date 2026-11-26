/**
 * "Practise this" (#144): the weak spot an analysis page found, as a playlist for a skill that keeps to it (its
 * ``focus``, read by the backend's ``domain/maps/focus.py``): streams at the weak speeds, jumps into the weak part of
 * the screen, sliders of the weak length, … A weak spot no map statistic can tell (a jump direction) has none.
 */

/** The skills a playlist can be made for (Goals & Training → Playlist for a skill). */
export type PractiseSkill = "aim" | "flow_aim" | "speed" | "stamina" | "accuracy" | "sliders" | "reading" | "consistency";

export const PRACTISABLE: ReadonlySet<string> = new Set<PractiseSkill>(
  ["aim", "flow_aim", "speed", "stamina", "accuracy", "sliders", "reading", "consistency"],
);

/** A playlist to practise: the skill, and the weak spot it keeps to (none: the whole skill). */
export interface Practise {
  skill: PractiseSkill;
  focus?: string;
}

/** The link that opens it on Goals & Training, where it is made at once. */
export function practiseUrl({ skill, focus }: Practise): string {
  const q = new URLSearchParams({ tab: "playlist", skill });
  if (focus) q.set("focus", focus);
  return `/skills?${q.toString()}`;
}

/** Ranges of whole steps (``from`` to ``to`` inclusive) of ``width``, the touching ones joined: [120, 140, 150] in
 * steps of 10 → "120-130,140-160". */
function ranges(starts: number[], width: number, digits = 0): string {
  const out: [number, number][] = [];
  for (const s of [...new Set(starts)].sort((a, b) => a - b)) {
    const last = out[out.length - 1];
    if (last && Math.abs(last[1] - s) < 1e-9) last[1] = s + width;
    else out.push([s, s + width]);
  }
  const n = (x: number) => String(Number(x.toFixed(digits)));
  return out.map(([lo, hi]) => `${n(lo)}-${n(hi)}`).join(",");
}

/** Streams at the weak speeds (the Stream speed chart's 10-BPM steps). */
export function streamSpeeds(bpms: number[]): Practise {
  return bpms.length ? { skill: "speed", focus: `bpm:${ranges(bpms, 10)}` } : { skill: "speed" };
}

/** Streams of the length where stamina gives in. */
export function streamLengths(notes: number[] | null | undefined): Practise {
  return notes?.length === 2 ? { skill: "stamina", focus: `run:${notes[0]}-${notes[1]}` } : { skill: "stamina" };
}

/** Reading at the weak approach rates ("AR 9.5": the chart's half steps). Maps have no AR above 10 without mods: those
 * steps practise at AR 10. */
export function approachRates(labels: string[]): Practise {
  const ars = labels.map((l) => Number(l.replace(/^AR\s*/, ""))).filter(Number.isFinite).map((ar) => Math.min(ar, 10));
  if (!ars.length) return { skill: "reading" };
  const focus = ranges(ars.filter((ar) => ar < 10), 0.5, 1);
  const ten = ars.some((ar) => ar >= 10) ? "10-11" : "";
  return { skill: "reading", focus: `ar:${[focus, ten].filter(Boolean).join(",")}` };
}

/** The kinds of jump the Aim page compares. */
export type AimKind = "direction" | "distance" | "angle" | "quadrant";

/** An aim weak spot by its kind and its label on the page. Close notes (under 2 circles apart) are spaced streams,
 * not jumps; a direction and a medium angle no map statistic tells: null. */
export function aimSpot(kind: AimKind, label: string): Practise | null {
  if (kind === "quadrant") return { skill: "aim", focus: `quadrant:${label}` };
  if (kind === "angle") {
    if (label.startsWith("sharp")) return { skill: "aim", focus: "angle:sharp" };
    if (label.startsWith("wide")) return { skill: "aim", focus: "angle:wide" };
    return null;
  }
  if (kind === "distance") {
    const lo = Number.parseFloat(label.replace("<", "0"));
    if (!Number.isFinite(lo)) return null;
    if (lo < 2) return { skill: "flow_aim" };
    return { skill: "aim", focus: lo >= 3 ? "jump:long" : "jump:short" };
  }
  return null;
}

/** Sliders of a weak stretch of lengths (whole circle diameters, ``from``–``to``) or speeds (diameters a second):
 * long or short, fast or slow for the maps. A stretch in the middle practises sliders as a whole. */
export function sliderStretch(by: "length" | "speed", from: number, to: number): Practise {
  if (by === "length") {
    if (from >= 2) return { skill: "sliders", focus: "slider_length:long" };
    if (to < 1) return { skill: "sliders", focus: "slider_length:short" };
  } else {
    if (from >= 9) return { skill: "sliders", focus: "slider_speed:fast" };
    if (to < 6) return { skill: "sliders", focus: "slider_speed:slow" };
  }
  return { skill: "sliders" };
}

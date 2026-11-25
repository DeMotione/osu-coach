/** The Aim page's groups of jumps in a player's words, for its verdicts and tooltips. */

export const jumpDirection = (label: string) => `jumps moving ${label}`;

/** "<0.5" / "0.5-1" / "4+" circle widths (diameters) from the previous note. */
export function jumpDistance(label: string): string {
  if (label.startsWith("<")) return `very short jumps (under ${label.slice(1)} circle)`;
  if (label.endsWith("+")) return `long jumps (${label} circle widths)`;
  return `jumps of ${label.replace("-", "–")} circle widths`;
}

const ANGLE_WORDS: Record<string, string> = {
  "sharp (<60°)": "back-and-forth jumps (sharp turns)",
  medium: "jumps that turn",
  "wide (>120°)": "jumps that keep going (wide angles)",
};

export const jumpAngle = (label: string) => ANGLE_WORDS[label] ?? `jumps at ${label} angles`;

/** Short labels for the angle chart's axis. */
export const ANGLE_SHORT: Record<string, string> = {
  "sharp (<60°)": "sharp turn",
  medium: "medium",
  "wide (>120°)": "keeps going",
};

export const screenPart = (label: string) => `notes in the ${label.replace("-", " ")} of the screen`;

/**
 * How far past (+) or short of (−) the note your clicks land along the jump, from ``along`` in circle radii: said in
 * circle widths a player can picture; under a tenth of a radius it is noise.
 */
export function overshoot(along: number | null): string | null {
  if (along === null || !Number.isFinite(along)) return null;
  if (Math.abs(along) < 0.1) return "You judge jump distance well: your clicks land neither short nor past the notes.";
  const width = Math.abs(along) / 2; // radii → circle widths
  const amount = width < 0.08 ? "a little" : width < 0.17 ? "about a tenth of a circle" : width < 0.3 ? "about a fifth of a circle" : "about a third of a circle or more";
  return along > 0
    ? `You overshoot: your clicks land ${amount} past the notes, along the jump.`
    : `You undershoot: your clicks land ${amount} short of the notes, along the jump.`;
}

/** The notes-weighted average over/undershoot of the distance groups with enough notes. */
export function averageAlong(rows: { along: number | null; objects: number }[], minNotes: number): number | null {
  let sum = 0;
  let n = 0;
  for (const r of rows) {
    if (r.along === null || r.objects < minNotes) continue;
    sum += r.along * r.objects;
    n += r.objects;
  }
  return n > 0 ? sum / n : null;
}

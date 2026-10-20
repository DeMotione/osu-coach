/**
 * osu!'s own star rating colours (lazer's difficulty spectrum): blue at the easy end, through green, yellow, red and
 * purple, to deep blue and black from 9★. Text on it is dark, and gold from 6.5★ like in the game.
 */

const STOPS: [number, string][] = [
  [0.1, "#4290fb"],
  [1.25, "#4fc0ff"],
  [2.0, "#4fffd5"],
  [2.5, "#7cff4f"],
  [3.3, "#f6f05c"],
  [4.2, "#ff8068"],
  [4.9, "#ff4e6f"],
  [5.8, "#c645b8"],
  [6.7, "#6563de"],
  [7.7, "#18158e"],
  [9.0, "#000000"],
];

const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const toHex = (c: number[]) => `#${c.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("")}`;

export function starColor(stars: number): string {
  if (stars < STOPS[0][0]) return "#aaaaaa";
  for (let i = 1; i < STOPS.length; i++) {
    const [s1, c1] = STOPS[i];
    if (stars <= s1) {
      const [s0, c0] = STOPS[i - 1];
      const k = (stars - s0) / (s1 - s0);
      const a = rgb(c0);
      const b = rgb(c1);
      return toHex(a.map((v, j) => v + (b[j] - v) * k));
    }
  }
  return STOPS[STOPS.length - 1][1];
}

export function starTextColor(stars: number): string {
  return stars >= 6.5 ? "#ffd966" : "rgb(0 0 0 / 0.75)";
}

/** From 9★ (black in osu!) a step is a milestone: a gold glow that grows to 13★. */
export function starGlow(stars: number): number {
  return stars < 9 ? 0 : Math.min(1, (stars - 8) / 5);
}

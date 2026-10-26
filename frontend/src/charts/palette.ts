/** Chart colours (the same in light and dark: they read on both). The osu! accents: pink, blue, purple, yellow, lime. */
export const C = {
  accent: "#ff66aa",
  good: "#88da20",
  bad: "#ff5a6e",
  muted: "#9a9a9a",
  info: "#66ccff",
  missRed: "#ff3b3b",
  warn: "#ffa51f",
  yellow: "#ffcc22",
  purple: "#aa88ff",
  orange: "#ff8e5d",
  cyan: "#2fd3df",
  brown: "#c39a8c",
} as const;

/** Dark text on a bright bar, and the outline of a marker on a plot: the darkest neutral of the CSS tokens. */
export const INK = "#141414";

/** Lines / bars of several series, in order. */
export const SERIES = [C.accent, C.info, C.purple, C.yellow, C.good, C.orange, C.cyan, C.brown];

/** Hit results as in the game: 300 blue, 100 green, 50 yellow. */
export const RESULT_COLORS: Record<number, string> = { 300: C.info, 100: C.good, 50: C.yellow };

export interface ChartTheme {
  dark: boolean;
  text: string;
  muted: string;
  line: string;
  split: string;
  tooltipBg: string;
  tooltipBorder: string;
  surface: string;
  heatLow: string;
}

/** Mirrors `--text`, `--muted`, `--surface` (the card) and `--raised` of `styles/tokens.css` (true neutrals). */
export function chartTheme(dark: boolean): ChartTheme {
  return dark
    ? {
        dark,
        text: "#ffffff",
        muted: "#b0b0b0",
        line: "rgba(255,255,255,0.26)",
        split: "rgba(255,255,255,0.08)",
        tooltipBg: "#3b3b3b",
        tooltipBorder: "rgba(255,255,255,0.1)",
        surface: "#1c1c1c",
        heatLow: "rgba(255,255,255,0.09)",
      }
    : {
        dark,
        text: "#121212",
        muted: "#616161",
        line: "rgba(0,0,0,0.2)",
        split: "rgba(0,0,0,0.07)",
        tooltipBg: "#ffffff",
        tooltipBorder: "rgba(0,0,0,0.12)",
        surface: "#ffffff",
        heatLow: "rgba(0,0,0,0.06)",
      };
}

/** Score colour of a 0–100 skill score (Overview): green ≥ 55, red ≤ 45, blue between, grey without one. */
export function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined || !Number.isFinite(score)) return C.muted;
  return score >= 55 ? C.good : score <= 45 ? C.bad : C.info;
}

/** A ``#rrggbb`` colour at opacity ``a`` (0–1) as ``rgba()``. */
export function alpha(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/** Mix the accent into the low heat colour by ``t`` (0–1): heat map cells. */
export function heat(t: number, theme: ChartTheme): string {
  const k = Math.max(0, Math.min(1, t));
  const a = 0.12 + 0.88 * k;
  return theme.dark ? `rgba(255,102,170,${a.toFixed(3)})` : `rgba(190,46,110,${(a * 0.9).toFixed(3)})`;
}

/** Text on a {@link heat} cell: white on strong colour, the theme's text colour on pale cells. */
export function heatText(t: number, theme: ChartTheme): string {
  return t > 0.55 || theme.dark ? "#ffffff" : theme.text;
}

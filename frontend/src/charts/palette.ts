/** Chart colours (the same in light and dark: they read on both) and theme-dependent text / grid colours. */
export const C = {
  accent: "#ff66aa",
  good: "#5fd3a0",
  bad: "#ff5c7a",
  muted: "#8b8fa3",
  info: "#6fb7ff",
  missRed: "#ff3b3b",
  warn: "#f5b041",
  yellow: "#ffb020",
  purple: "#c792ea",
  orange: "#ff8c5a",
  cyan: "#4dd0e1",
  brown: "#a1887f",
} as const;

/** Lines / bars of several series, in order. */
export const SERIES = [C.accent, C.info, C.good, C.yellow, C.purple, C.orange, C.cyan, C.brown];

export const RESULT_COLORS: Record<number, string> = { 300: C.good, 100: C.info, 50: C.yellow };

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

export function chartTheme(dark: boolean): ChartTheme {
  return dark
    ? {
        dark,
        text: "#d9dae4",
        muted: "#8b8fa3",
        line: "rgba(255,255,255,0.18)",
        split: "rgba(255,255,255,0.06)",
        tooltipBg: "#282836",
        tooltipBorder: "rgba(255,255,255,0.14)",
        surface: "#181822",
        heatLow: "rgba(128,128,160,0.14)",
      }
    : {
        dark,
        text: "#2b2c38",
        muted: "#6c6f82",
        line: "rgba(20,20,40,0.22)",
        split: "rgba(20,20,40,0.07)",
        tooltipBg: "#ffffff",
        tooltipBorder: "rgba(20,20,40,0.14)",
        surface: "#ffffff",
        heatLow: "rgba(128,128,160,0.12)",
      };
}

/** Score colour of a 0–100 skill score (Overview): green ≥ 55, red ≤ 45, blue between, grey without one. */
export function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined || !Number.isFinite(score)) return C.muted;
  return score >= 55 ? C.good : score <= 45 ? C.bad : C.info;
}

/** Mix the accent into the low heat colour by ``t`` (0–1): heat map cells. */
export function heat(t: number, theme: ChartTheme): string {
  const k = Math.max(0, Math.min(1, t));
  const a = 0.12 + 0.88 * k;
  return theme.dark ? `rgba(255,102,170,${a.toFixed(3)})` : `rgba(214,51,127,${(a * 0.9).toFixed(3)})`;
}

/** Text on a {@link heat} cell: white on strong colour, the theme's text colour on pale cells. */
export function heatText(t: number, theme: ChartTheme): string {
  return t > 0.55 || theme.dark ? "#ffffff" : theme.text;
}

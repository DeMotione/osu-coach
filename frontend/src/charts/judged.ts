/**
 * Bars of groups judged against your usual miss rate (lib/verdict): red = clearly worse, green = clearly better,
 * grey = as usual, faint = too few notes to tell; a dashed line at your average, each bar's own count in its
 * tooltip. One axis, the value on each bar: what stands out reads without the axis.
 */
import { esc } from "../lib/format";
import { share, times, type Judged } from "../lib/verdict";
import { base, categoryAxis, grid, niceMax, responsive, tooltip, valueAxis } from "./base";
import type { Option } from "./echarts";
import { C, faded, type ChartTheme } from "./palette";
import { params } from "./types";

export interface JudgedBars {
  groups: Judged[];
  /** what the groups count: "jumps", "notes", "sliders" */
  unit: string;
  /** bars sideways, sorted worst first (groups without an order, like directions); else upright in their order */
  sideways?: boolean;
  /** the name of the groups' axis (upright bars), e.g. "jump distance (circle widths)" */
  axisName?: string;
  /** how a group is named in its tooltip: "jumps moving right" */
  describe?: (label: string) => string;
  /** a second line on an upright bar, e.g. its counts "5/68" (left out on narrow charts); by the group's place */
  count?: (index: number) => string;
  /** one more line in a group's tooltip; by the group's place */
  detail?: (index: number) => string;
}

/** A bar's colour for what it says. */
export function standingColor(g: Judged, t: ChartTheme): string {
  switch (g.standing) {
    case "worse":
      return C.bad;
    case "better":
      return C.good;
    case "few":
      return faded(t.dark ? "#ffffff" : "#000000", 0.14, t.surface);
    default:
      return faded(t.dark ? "#ffffff" : "#000000", 0.38, t.surface);
  }
}

export function judgedBars({ groups, unit, sideways = false, axisName, describe, count, detail }: JudgedBars, t: ChartTheme): Option {
  const shown = sideways ? [...groups].sort((a, b) => (a.rate ?? -1) - (b.rate ?? -1)) : groups;
  const usual = groups.find((g) => g.usual !== null)?.usual ?? null;
  const max = Math.max(...shown.map((g) => (g.rate ?? 0) * 100), (usual ?? 0) * 100, 1);
  const values = shown.map((g) => ({
    value: g.rate === null ? 0 : +(g.rate * 100).toFixed(2),
    itemStyle: { color: standingColor(g, t), borderRadius: sideways ? [0, 3, 3, 0] : [3, 3, 0, 0] },
    label: {
      color: g.standing === "few" ? t.muted : g.standing === "usual" ? t.text : g.standing === "worse" ? C.bad : C.good,
      fontWeight: g.standing === "worse" || g.standing === "better" ? 700 : 400,
    },
  }));
  // the dashed line at your average; the card says what it is (a label on the line got in the bars' way)
  const usualLine = usual === null
    ? undefined
    : {
        silent: true,
        symbol: "none",
        z: 1, // behind the bars and their labels
        lineStyle: { color: t.muted, type: "dashed", width: 1 },
        label: { show: false },
        data: [sideways ? { xAxis: +(usual * 100).toFixed(2) } : { yAxis: +(usual * 100).toFixed(2) }],
      };
  const rateAxis = valueAxis(t, {
    min: 0,
    max: niceMax(max, max > 16 ? 10 : max > 8 ? 5 : 1, 1.25, 100),
    axisLabel: { formatter: (v: number) => `${v}%` },
    ...(sideways ? {} : { name: "missed", nameGap: 36, nameRotate: 90 }),
  });
  const groupAxis = categoryAxis(
    t,
    shown.map((g) => g.label),
    sideways
      ? { axisLabel: { color: t.text, fontSize: 12 } }
      : { name: axisName, nameGap: 26, axisLabel: { color: t.text, interval: 0 } },
  );
  const rateLabel = (p: unknown) => {
    const g = shown[params(p)[0].dataIndex];
    return g.standing === "few" ? (g.rate === null ? "–" : `${share(g.rate)}?`) : share(g.rate);
  };
  const option = base(t, {
    grid: grid({ right: sideways ? 54 : 14, bottom: sideways ? 6 : 8, ...(count ? { top: 34 } : {}) }),
    tooltip: tooltip(t, {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: t.split } },
      formatter: (p: unknown) => {
        const g = shown[params(p)[0].dataIndex];
        const name = esc(describe ? describe(g.label) : g.label);
        const n = `${Math.round(g.n)} ${unit}`;
        if (g.rate === null) return `<b>${name}</b><br>no ${unit}`;
        const more = detail ? `<br>${esc(detail(groups.indexOf(g)))}` : "";
        if (g.standing === "few") return `<b>${name}</b><br>${share(g.rate)} missed · only ${n}: too few to tell${more}`;
        const vs = g.ratio !== null ? `<br>${times(g.ratio)} your average (${share(g.usual)})` : "";
        return `<b>${name}</b><br>${share(g.rate)} missed · ${n}${more}${vs}`;
      },
    }),
    xAxis: sideways ? rateAxis : groupAxis,
    yAxis: sideways ? groupAxis : rateAxis,
    series: [
      {
        type: "bar",
        barMaxWidth: sideways ? 22 : 44,
        data: values,
        label: {
          show: true,
          position: sideways ? "right" : "top",
          fontSize: 11.5,
          lineHeight: 15,
          // an outline in the card's colour, so the dashed line doesn't strike a label through
          textBorderColor: t.surface,
          textBorderWidth: 3,
          formatter: (p: unknown) => {
            const g = shown[params(p)[0].dataIndex];
            const c = count?.(groups.indexOf(g));
            return c ? `${rateLabel(p)}\n${c}` : rateLabel(p);
          },
        },
        markLine: usualLine,
      },
    ],
  });
  // narrow: the share alone, smaller, so neighbours' labels keep apart
  return count ? responsive(option, { series: [{ label: { formatter: rateLabel, fontSize: 10 } }] }) : option;
}

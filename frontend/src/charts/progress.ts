import type { Schemas } from "../api/client";
import { esc } from "../lib/format";
import { type Period, periodStart, timeline } from "../lib/progressTime";
import { base, grid, legend, refLine, timeAxis, tooltip, valueAxis } from "./base";
import type { Option } from "./echarts";
import { C, SERIES, type ChartTheme } from "./palette";
import { params } from "./types";

type Row = Schemas["PeriodRow"];

/** Your comfort level and your hardest clean pass on a real timeline: periods without plays are gaps, not joined. */
export function starsChart(all: Row[], period: Period, t: ChartTheme): Option {
  const lines: [keyof Row, string, string, number][] = [
    ["comfort_stars", "comfort", C.accent, 3],
    ["max_stars_passed", "hardest clean pass", C.info, 1.5],
  ];
  const byStart = new Map(all.map((r) => [periodStart(r.key)?.getTime(), r]));
  return base(t, {
    grid: grid({}, true),
    legend: legend(t),
    tooltip: tooltip(t, {
      trigger: "axis",
      formatter: (p: unknown) => {
        const ps = params(p).filter((x) => Array.isArray(x.value) && (x.value as unknown[])[1] !== null);
        const r = ps.length ? byStart.get((ps[0].value as [number])[0]) : undefined;
        if (!r) return "";
        const head = `<b>${esc(r.key)}</b> · ${r.plays} plays${r.few_plays ? " (few: rough numbers)" : ""}`;
        return [head, ...ps.map((x) => `${x.marker ?? ""}${esc(x.seriesName ?? "")}: ${((x.value as [number, number])[1]).toFixed(2)}★`)].join("<br>");
      },
    }),
    xAxis: timeAxis(t),
    yAxis: valueAxis(t, { name: "star rating ★", nameGap: 40, nameRotate: 90, scale: true }),
    series: lines.map(([key, name, color, width]) => ({
      name,
      type: "line",
      connectNulls: false,
      data: timeline(all, period, (r) => r[key] as number | null).map(([time, v]) => ({
        value: [time, v],
        symbol: byStart.get(time)?.few_plays ? "emptyCircle" : "circle",
      })),
      symbolSize: 7,
      lineStyle: { color, width },
      itemStyle: { color },
    })),
  });
}

type Goal = Schemas["GoalHistory"];

/** Where a goal is to be: its target at its deadline (the end of its path). */
const goalPoint = (h: Goal) => h.target.at(-1);

const DOT_GAP = 14; // px between goal dots side by side

/** Goal labels that would overlap move apart up or down (a line leads to the dot). Pinned where they are first: a label
 * left at its place beside the dot is put back there on the next redraw, losing the move. */
export const goalLabelLayout = (p: { labelRect: { x: number; y: number } }) => ({
  x: p.labelRect.x,
  y: p.labelRect.y,
  align: "left",
  verticalAlign: "top",
  moveOverlap: "shiftY",
});

/** Goal dots that would sit on each other (the same axis and deadline, targets closer than ``near`` in the axis' unit)
 * go side by side: each one's sideways ``offset`` (px) and the ``spread`` of its row each way from the middle. A 4-week
 * plan sets its goals on one day, with targets often a few points apart. */
export function goalOffsets(history: Goal[], near: (unit: string) => number): Map<string, { offset: number; spread: number }> {
  const groups = new Map<string, Goal[]>();
  for (const h of history) {
    const at = goalPoint(h);
    if (at === undefined || at.score === null) continue;
    const key = `${h.unit ?? "score"} ${at.day}`;
    groups.set(key, [...(groups.get(key) ?? []), h]);
  }
  const target = (h: Goal) => goalPoint(h)?.score ?? 0;
  const out = new Map<string, { offset: number; spread: number }>();
  for (const group of groups.values()) {
    group.sort((a, b) => target(a) - target(b));
    let cluster: Goal[] = [];
    const flush = () => {
      const spread = ((cluster.length - 1) / 2) * DOT_GAP;
      cluster.forEach((h, i) => out.set(h.goal_id, { offset: i * DOT_GAP - spread, spread }));
      cluster = [];
    };
    for (const h of group) {
      const last = cluster.at(-1);
      if (last && target(h) - target(last) >= near(h.unit ?? "score")) flush();
      cluster.push(h);
    }
    flush();
  }
  return out;
}

/** The goal skills on a real timeline (a time axis: two weeks are twice as wide as one): one line per skill (the plays
 * so far) and a labelled dot for each goal at its target and deadline, with today marked. Dots that would sit on each
 * other go side by side and labels that would overlap move apart; hovering a skill brings it forward.
 * ``today``: YYYY-MM-DD. */
export function goalsChart(history: Goal[], t: ChartTheme, today = localDay()): Option {
  const pairs = (pts: Schemas["HistoryPoint"][]) => pts.filter((p) => p.score !== null).map((p) => [p.day, p.score]);
  // goals in stars (Star Levels, #129) on a star axis; scores (and consistency there) on the 0–100 one
  const units = [...new Set(history.map((h) => h.unit ?? "score"))].sort((a, b) => (a === "stars" ? -1 : b === "stars" ? 1 : 0));
  const axis = (unit: string, i: number) =>
    unit === "stars"
      ? valueAxis(t, { name: "★", nameGap: 32, nameRotate: 90, scale: true, position: i ? "right" : "left", axisLabel: { formatter: (v: number) => `${v}★` } })
      : valueAxis(t, { name: "score", nameGap: 32, nameRotate: 90, min: 0, max: 100, position: i ? "right" : "left", ...(i ? { splitLine: { show: false } } : {}) });
  const shown = (unit: string) => (v: number | null) => (v === null || v === undefined ? "–" : unit === "stars" ? `${v.toFixed(2)}★` : v.toFixed(0));
  // one line per skill: a reached goal and the next one for the same skill share it
  const bySkill = new Map<string, Goal[]>();
  for (const h of history) bySkill.set(h.skill, [...(bySkill.get(h.skill) ?? []), h]);
  // "close" dots: 5 points on the score axis, 5% of the stars shown on the star axis
  const stars = history.filter((h) => h.unit === "stars").flatMap((h) => [...h.points, ...h.target].flatMap((p) => (p.score === null ? [] : [p.score])));
  const starSpan = stars.length ? Math.max(Math.max(...stars) - Math.min(...stars), 0.5) : 1;
  const offsets = goalOffsets(history, (unit) => (unit === "stars" ? starSpan * 0.05 : 5));
  // a label goes on the side of its dot with more room
  const days = history.flatMap((h) => [...h.points, ...h.target].map((p) => Date.parse(p.day)));
  const middle = days.length ? (Math.min(...days) + Math.max(...days)) / 2 : 0;
  return base(t, {
    grid: grid(units.length > 1 ? { right: 56 } : {}, true),
    legend: legend(t),
    tooltip: tooltip(t, { trigger: "axis" }),
    // a little room before the first day and after the last deadline, for their dots
    xAxis: valueAxis(t, {
      type: "time",
      min: (e: { min: number; max: number }) => e.min - (e.max - e.min) * 0.03,
      max: (e: { min: number; max: number }) => e.max + (e.max - e.min) * 0.03,
      splitLine: { show: false },
      axisLabel: { formatter: "{MMM} {d}", hideOverlap: true },
    }),
    yAxis: units.length > 1 ? units.map(axis) : axis(units[0] ?? "score", 0),
    series: [...bySkill.values()].map((goals, i) => {
      const color = SERIES[i % SERIES.length];
      const unit = goals[0].unit ?? "score";
      const line = pairs(goals[0].points);
      const dots = goals.flatMap((g) => {
        const at = goalPoint(g);
        if (at === undefined || at.score === null) return [];
        const { offset, spread } = offsets.get(g.goal_id) ?? { offset: 0, spread: 0 };
        const right = Date.parse(at.day) < middle;
        // a gap first ([null, null]: on no day, so never in the tooltip), so the line doesn't run on to the dot
        return [
          [null, null],
          {
            value: [at.day, at.score],
            symbol: "diamond",
            symbolSize: 15,
            symbolOffset: [offset, 0],
            itemStyle: { color, borderColor: t.surface, borderWidth: 1.5 },
            label: {
              show: true,
              position: right ? "right" : "left",
              distance: 8 + spread + (right ? -offset : offset), // past the whole row of dots, not over one of them
              formatter: `${g.label} goal`,
              color,
              fontSize: 11.5,
              fontWeight: 600,
              backgroundColor: t.surface,
              padding: [2, 5],
              borderRadius: 4,
            },
          },
        ];
      });
      return {
        name: goals[0].label,
        type: "line",
        data: [...line, ...dots],
        symbolSize: 7,
        lineStyle: { color, width: 2 },
        itemStyle: { color },
        emphasis: { focus: "series" },
        labelLayout: goalLabelLayout,
        labelLine: { show: true, lineStyle: { color, width: 1, opacity: 0.7 } },
        tooltip: { valueFormatter: (v: number | null, index: number) => (index >= line.length ? `goal ${shown(unit)(v)}` : shown(unit)(v)) },
        ...(units.length > 1 ? { yAxisIndex: units.indexOf(unit) } : {}),
        ...(i === 0 ? { markLine: refLine(t, { xAxis: today }, t.muted, { label: { show: true, formatter: "today", color: t.muted } }) } : {}),
      };
    }),
  });
}

function localDay(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

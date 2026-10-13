import type { Schemas } from "../api/client";
import { esc } from "../lib/format";
import { base, categoryAxis, grid, niceMax, refLine, responsive, tooltip, valueAxis } from "./base";
import type { Option } from "./echarts";
import { C, scoreColor, type ChartTheme } from "./palette";
import { params } from "./types";

type Skill = Schemas["SkillScore"];
type SkillMeta = Schemas["SkillMeta"];

export const MISS_SHORT: Record<string, string> = {
  aim: "Aim",
  speed_aim: "Speed-aim (streams)",
  early: "Too early",
  late: "Too late",
  no_tap: "No tap",
  lost: "Lost track",
  notelock: "Notelock",
};

/** What a skill measures, how it is scored, the player's numbers and what raises it (the bar's hover). */
export function skillHover(s: Skill, help?: SkillMeta): string {
  const p = (text: string, cls = "") => `<div style="margin-top:6px${cls}">${esc(text)}</div>`;
  let html = `<b>${esc(s.label)}: ${esc(s.score_text)}</b>`;
  if (s.too_few_misses)
    html += p(
      "You barely miss on these notes, so there is nothing to compare: this score counts misses against what the difficulty predicts. That is a good sign, not a gap.",
    );
  if (help) html += p(help.what) + p(help.how);
  html += p(`You: ${s.facts.join("; ")}`);
  if (help) html += p(`To raise it: ${help.practise}`);
  return html;
}

const SKILL_AXIS = (t: ChartTheme, labels: string[], width: number) =>
  categoryAxis(t, labels, {
    inverse: true,
    axisLabel: { color: t.text, fontSize: 12, width, overflow: "break", lineHeight: 15 },
  });

const NARROW_SKILLS = (right: number) => ({
  grid: { right },
  yAxis: { axisLabel: { width: 92, fontSize: 11 } },
  series: [{ label: { fontSize: 11 } }],
});

export function skillBars(skills: Skill[], help: SkillMeta[], t: ChartTheme): Option {
  const helpOf = Object.fromEntries(help.map((h) => [h.key, h]));
  return responsive(
    base(t, {
      grid: grid({ right: 96, bottom: 8 }),
      xAxis: valueAxis(t, { min: 0, max: 100, interval: 25, name: "50 = typical for your level · higher is better", nameGap: 26 }),
      yAxis: SKILL_AXIS(
        t,
        skills.map((s) => s.label),
        230,
      ),
      tooltip: tooltip(t, {
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: t.split } },
        formatter: (p: unknown) => {
          const s = skills[params(p)[0].dataIndex];
          return skillHover(s, helpOf[s.key]);
        },
      }),
      series: [
        {
          type: "bar",
          barMaxWidth: 22,
          data: skills.map((s) => ({
            value: s.score ?? 0,
            itemStyle: { color: scoreColor(s.score), borderRadius: [0, 5, 5, 0] },
          })),
          label: {
            show: true,
            position: "right",
            color: t.text,
            fontSize: 12,
            formatter: (p: unknown) => skills[params(p)[0].dataIndex].score_text,
          },
          markLine: refLine(t, { xAxis: 50 }),
        },
      ],
    }),
    NARROW_SKILLS(80),
  );
}

export function topBars(top: Schemas["TopSkill"][], t: ChartTheme): Option {
  return responsive(
    base(t, {
      grid: grid({ right: 34, bottom: 8 }),
      xAxis: valueAxis(t, { min: 0, max: 100, interval: 25, name: "50 = typical for a 10★ player · ◆ = top players", nameGap: 26 }),
      yAxis: SKILL_AXIS(
        t,
        top.map((s) => s.label),
        230,
      ),
      tooltip: tooltip(t, {
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: t.split } },
        formatter: (p: unknown) => {
          const s = top[params(p)[0].dataIndex];
          const you = s.score === null ? "not enough data" : s.score.toFixed(0);
          const tp = s.top === null ? "–" : s.top.toFixed(0);
          return `<b>${esc(s.label)}</b><br>you ${esc(you)} · top players ${esc(tp)} (50 = typical 10★ player)`;
        },
      }),
      series: [
        {
          type: "bar",
          name: "you",
          barMaxWidth: 22,
          data: top.map((s) => ({ value: s.score ?? 0, itemStyle: { color: scoreColor(s.score), borderRadius: [0, 5, 5, 0] } })),
          label: {
            show: true,
            position: "insideRight",
            color: "#16161f",
            fontWeight: 600,
            formatter: (p: unknown) => {
              const s = top[params(p)[0].dataIndex];
              return s.score === null || s.score < 12 ? "" : s.score.toFixed(0);
            },
          },
        },
        {
          type: "scatter",
          name: "top players",
          symbol: "diamond",
          symbolSize: 13,
          itemStyle: { color: t.dark ? "#c9cbd8" : "#6c6f82" },
          data: top.map((s) => s.top),
          z: 3,
        },
      ],
    }),
    NARROW_SKILLS(14),
  );
}

export function missCauses(causes: Schemas["MissCause"][], descriptions: Record<string, string>, t: ChartTheme): Option {
  const items = [...causes].sort((a, b) => a.share - b.share);
  const max = Math.max(...items.map((c) => c.share * 100), 1);
  return base(t, {
    grid: grid({ right: 16, bottom: 8 }),
    xAxis: valueAxis(t, {
      min: 0,
      max: niceMax(max, 10, 1.18, 100),
      name: "% of misses",
      nameGap: 26,
      axisLabel: { formatter: (v: number) => `${v}%` },
    }),
    yAxis: categoryAxis(
      t,
      items.map((c) => MISS_SHORT[c.cause] ?? c.cause),
      { axisLabel: { color: t.text, fontSize: 12 } },
    ),
    tooltip: tooltip(t, {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: t.split } },
      formatter: (p: unknown) => {
        const c = items[params(p)[0].dataIndex];
        return `${esc(descriptions[c.cause] ?? c.cause)}<br>${c.misses} misses (unweighted)`;
      },
    }),
    series: [
      {
        type: "bar",
        barMaxWidth: 20,
        data: items.map((c) => +(c.share * 100).toFixed(2)),
        itemStyle: { color: C.accent, borderRadius: [0, 5, 5, 0] },
        label: { show: true, position: "right", color: t.text, formatter: (p: unknown) => `${Math.round(Number(params(p)[0].value))}%` },
      },
    ],
  });
}

import type { Schemas } from "../api/client";
import { esc } from "../lib/format";
import { feltHarder, outOfReachFrom, scoreAt, starLabel } from "../lib/starCompare";
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
  if (help) html += p(help.what);
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
      xAxis: valueAxis(t, { min: 0, max: 100, interval: 25, name: "50 = assumed comfort baseline · higher is better", nameGap: 26 }),
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
            itemStyle: { color: scoreColor(s.score), borderRadius: [0, 3, 3, 0] },
          })),
          label: {
            show: true,
            position: "right",
            color: t.text,
            fontSize: 12,
            formatter: (p: unknown) => skills[params(p)[0].dataIndex].score?.toFixed(0) ?? "–",
          },
          markLine: refLine(t, { xAxis: 50 }),
        },
      ],
    }),
    NARROW_SKILLS(80),
  );
}

/** The hover of a bar on the comparison chart: the score there, how it comes from the comfort-level score, the
 * player's numbers and (with the skill's help text) what the skill is and what raises it. */
export function compareHover(s: Skill, comfort: number, target: number, help?: SkillMeta): string {
  const p = (text: string) => `<div style="margin-top:6px">${esc(text)}</div>`;
  const at = starLabel(target);
  const here = scoreAt(s.score, comfort, target);
  if (here === null) return `<b>${esc(s.label)} at ${esc(at)}: ${esc(s.score_text)}</b>${help ? p(help.what) : ""}`;
  const felt = feltHarder(comfort, target);
  const from = `${(s.score as number).toFixed(0)} at your ${starLabel(comfort)} comfort level`;
  const how =
    Math.abs(felt) < 0.005
      ? `${at} is your comfort level`
      : felt > 0
        ? `${at} feels ${Math.round(felt * 100)}% harder, so ${from} drops by that much; every skill is out of reach from ${outOfReachFrom(comfort).toFixed(1)}★`
        : `${at} feels ${Math.round(-felt * 100)}% easier, so ${from} closes that much of its gap to 100`;
  let html = `<b>${esc(s.label)} at ${esc(at)}: ${here.toFixed(0)}</b>`;
  if (help) html += p(help.what);
  html += p(how);
  html += p(`You: ${s.facts.join("; ")}`);
  if (help) html += p(`To raise it: ${help.practise}`);
  return html;
}

export function compareBars(skills: Skill[], comfort: number, target: number, t: ChartTheme, help: SkillMeta[] = []): Option {
  const helpOf = Object.fromEntries(help.map((h) => [h.key, h]));
  const scores = skills.map((s) => scoreAt(s.score, comfort, target));
  return responsive(
    base(t, {
      grid: grid({ right: 96, bottom: 8 }),
      xAxis: valueAxis(t, { min: 0, max: 100, interval: 25, name: `Your scores at ${starLabel(target)} · 0 = out of reach`, nameGap: 26 }),
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
          return compareHover(s, comfort, target, helpOf[s.key]);
        },
      }),
      series: [
        {
          type: "bar",
          barMaxWidth: 22,
          data: scores.map((v) => ({ value: v ?? 0, itemStyle: { color: scoreColor(v), borderRadius: [0, 3, 3, 0] } })),
          label: {
            show: true,
            position: "right",
            color: t.text,
            fontSize: 12,
            formatter: (p: unknown) => {
              const v = scores[params(p)[0].dataIndex];
              return v === null ? "–" : v === 0 ? "out of reach" : v.toFixed(0);
            },
          },
        },
      ],
    }),
    NARROW_SKILLS(80),
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
        itemStyle: { color: C.accent, borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: "right", color: t.text, formatter: (p: unknown) => `${Math.round(Number(params(p)[0].value))}%` },
      },
    ],
  });
}

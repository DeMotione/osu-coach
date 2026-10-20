import type { Schemas } from "../api/client";
import { esc } from "../lib/format";
import { gapLabel, levelLabel, starLabel } from "../lib/starCompare";
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

type SkillLevel = Schemas["SkillLevel"];
type CompareTarget = Schemas["CompareTarget"];

/** The hover of a bar on the comparison chart: the skill's star level, the gap to the star rating compared with,
 * the player's numbers and (with the skill's help text) what the skill is and what raises it. */
export function compareHover(s: Skill, level: SkillLevel | undefined, target: CompareTarget, help?: SkillMeta): string {
  const p = (text: string) => `<div style="margin-top:6px">${esc(text)}</div>`;
  const at = starLabel(target.stars);
  const row = target.skills.find((k) => k.key === s.key);
  if (!level || level.level === null || !row || row.gap === null || row.score === null)
    return `<b>${esc(s.label)} at ${esc(at)}: not enough data for a level</b>${help ? p(help.what) : ""}`;
  const lv = levelLabel(level);
  const gap = row.gap;
  let html = `<b>${esc(s.label)} at ${esc(at)}: ${row.score.toFixed(0)} (${esc(gapLabel(gap))})</b>`;
  if (help) html += p(help.what);
  html += p(
    level.bound === "at_least"
      ? `Your level: ${lv}. You held nearly everything you played${level.tested === null ? "" : ` (the hardest like ${starLabel(level.tested)} maps)`}, so it may be higher.`
      : level.bound === "at_most"
        ? `Your level: ${lv}, below what the easiest maps demand.`
        : `Your level: ${lv}: you showed what typical ${lv} maps demand.`,
  );
  const by = gapLabel(Math.abs(gap)).slice(1);
  html += p(
    Math.abs(gap) < 0.05
      ? `Just what typical ${at} maps demand (50 = just ready, 10 points per star).`
      : `${by} ${gap > 0 ? "above" : "short of"} what typical ${at} maps demand (50 = just ready, 10 points per star).`,
  );
  html += p(`You: ${s.facts.join("; ")}`);
  if (help) html += p(`To raise it: ${help.practise}`);
  return html;
}

export function compareBars(skills: Skill[], levels: SkillLevel[], target: CompareTarget, t: ChartTheme, help: SkillMeta[] = []): Option {
  const helpOf = Object.fromEntries(help.map((h) => [h.key, h]));
  const levelOf = Object.fromEntries(levels.map((l) => [l.key, l]));
  const rowOf = Object.fromEntries(target.skills.map((k) => [k.key, k]));
  const rows = skills.map((s) => rowOf[s.key]);
  return responsive(
    base(t, {
      grid: grid({ right: 96, bottom: 8 }),
      xAxis: valueAxis(t, {
        min: 0,
        max: 100,
        interval: 25,
        name: `Against typical ${starLabel(target.stars)} maps · 50 = just ready, 10 per star`,
        nameGap: 26,
      }),
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
          return compareHover(s, levelOf[s.key], target, helpOf[s.key]);
        },
      }),
      series: [
        {
          type: "bar",
          barMaxWidth: 22,
          data: rows.map((r) => ({
            value: r?.score ?? 0,
            itemStyle: { color: scoreColor(r?.score ?? null), borderRadius: [0, 3, 3, 0] },
          })),
          label: {
            show: true,
            position: "right",
            color: t.text,
            fontSize: 12,
            formatter: (p: unknown) => {
              const i = params(p)[0].dataIndex;
              const gap = rows[i]?.gap ?? null;
              if (gap === null) return "–";
              const bound = levelOf[skills[i].key]?.bound;
              return `${bound === "at_least" ? "≥ " : bound === "at_most" ? "≤ " : ""}${gapLabel(gap)}`;
            },
          },
          markLine: refLine(t, { xAxis: 50 }),
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

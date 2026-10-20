import type { Schemas } from "../api/client";
import { esc } from "../lib/format";
import { feltHarder, outOfReachFrom, readiness, starLabel } from "../lib/readiness";
import { base, categoryAxis, grid, niceMax, responsive, tooltip, valueAxis } from "./base";
import type { Option } from "./echarts";
import { C, scoreColor, type ChartTheme } from "./palette";
import { params } from "./types";

type SkillLevel = Schemas["SkillLevel"];
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

/** The hover of a readiness bar: the skill's level, how much harder the target feels, what the level is measured
 * from, and (with the skill's help text) what the skill is and what raises it. */
export function readinessHover(s: SkillLevel, target: number, help?: SkillMeta): string {
  const p = (text: string) => `<div style="margin-top:6px">${esc(text)}</div>`;
  const at = starLabel(target);
  if (s.level === null) return `<b>${esc(s.label)}: not enough data yet</b>${help ? p(help.what) : ""}`;
  const ready = readiness(s.level, target) ?? 0;
  const felt = feltHarder(s.level, target);
  let html = `<b>${esc(s.label)}: ${Math.round(ready * 100)}% ready for ${esc(at)}</b>`;
  if (help) html += p(help.what);
  html += p(
    `Level ${s.level.toFixed(1)}★: ` +
      (felt <= 0 ? `${at} is within it` : `${at} feels ${Math.round(felt * 100)}% harder; out of reach from ${outOfReachFrom(s.level).toFixed(1)}★`),
  );
  html += p(`From ${s.facts.join("; ")}`);
  if (help) html += p(`To raise it: ${help.practise}`);
  return html;
}

export function readinessBars(skills: SkillLevel[], target: number, t: ChartTheme, help: SkillMeta[] = []): Option {
  const helpOf = Object.fromEntries(help.map((h) => [h.key, h]));
  const ready = skills.map((s) => readiness(s.level, target));
  return responsive(
    base(t, {
      grid: grid({ right: 96, bottom: 8 }),
      xAxis: valueAxis(t, { min: 0, max: 100, interval: 25, name: `% ready for ${starLabel(target)} · 0 = out of reach`, nameGap: 26 }),
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
          return readinessHover(s, target, helpOf[s.key]);
        },
      }),
      series: [
        {
          type: "bar",
          barMaxWidth: 22,
          data: ready.map((r) => ({
            value: r === null ? 0 : Math.round(r * 100),
            itemStyle: { color: scoreColor(r === null ? null : r * 100), borderRadius: [0, 3, 3, 0] },
          })),
          label: {
            show: true,
            position: "right",
            color: t.text,
            fontSize: 12,
            formatter: (p: unknown) => {
              const r = ready[params(p)[0].dataIndex];
              return r === null ? "–" : r === 0 ? "out of reach" : `${Math.round(r * 100)}%`;
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

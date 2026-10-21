import type { Schemas } from "../api/client";
import { esc } from "../lib/format";
import { changeLabel, starLabel } from "../lib/starCompare";
import { base, categoryAxis, grid, niceMax, refLine, responsive, tooltip, valueAxis } from "./base";
import type { Option } from "./echarts";
import { C, alpha, scoreColor, type ChartTheme } from "./palette";
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

type CompareTarget = Schemas["CompareTarget"];

/** The hover of a bar on the comparison chart: the score at the star rating picked, how it comes from the comfort-level
 * score, the player's numbers and (with the skill's help text) what the skill is and what raises it. */
export function compareHover(s: Skill, target: CompareTarget, comfort: number, help?: SkillMeta): string {
  const p = (text: string) => `<div style="margin-top:6px">${esc(text)}</div>`;
  const at = starLabel(target.stars);
  const row = target.skills.find((k) => k.key === s.key);
  // measured on the player's own maps of that star rating (consistency), not moved from the comfort-level score
  if (row && row.maps !== null) {
    if (row.score === null)
      return `<b>${esc(s.label)} at ${esc(at)}: Not enough data</b>${row.needs ? p(`To get a score: ${row.needs}`) : ""}${help ? p(help.what) : ""}`;
    const vs = s.score === null || target.comfort ? "" : ` (${changeLabel(row.change ?? 0)} against your comfort level)`;
    let html = `<b>${esc(s.label)} at ${esc(at)}: ${row.score.toFixed(0)}${esc(vs)}</b>`;
    if (help) html += p(help.what);
    html += p(`Measured on your ${row.maps} different maps from ${starLabel(target.stars - 1)} to ${at} (the closer to ${at}, the more a map counts); the more maps you play there, the more reliable it is.`);
    if (help) html += p(`To raise it: ${help.practise}`);
    return html;
  }
  if (!row || row.score === null || s.score === null)
    return `<b>${esc(s.label)} at ${esc(at)}: ${esc(s.score_text)}</b>${help ? p(help.what) : ""}`;
  const change = row.change ?? 0;
  let html = `<b>${esc(s.label)} at ${esc(at)}: ${row.score.toFixed(0)}${target.comfort ? "" : ` (${esc(changeLabel(change))})`}</b>`;
  if (help) html += p(help.what);
  if (target.comfort) html += p(`${at} is your comfort level: the score above.`);
  else if (row.demand !== null) {
    const more = Math.round(Math.abs(row.demand - 1) * 100);
    const what = `Typical ${at} maps demand ${more}% ${row.demand >= 1 ? "more" : "less"} of this skill than maps of your ${starLabel(comfort)} comfort level`;
    html += p(
      Math.round(change) === 0
        ? `${what}, so ${s.score.toFixed(0)} stays at ${row.score.toFixed(0)}.`
        : `${what}, so ${s.score.toFixed(0)} ${change < 0 ? "drops" : "rises"} to ${row.score.toFixed(0)}.`,
    );
  }
  html += p(`You: ${s.facts.join("; ")}`);
  if (help) html += p(`To raise it: ${help.practise}`);
  return html;
}

/** The comfort-level scores (faded) and the scores at the star rating picked, with the change between them. */
export function compareBars(skills: Skill[], target: CompareTarget, comfort: number, t: ChartTheme, help: SkillMeta[] = []): Option {
  const helpOf = Object.fromEntries(help.map((h) => [h.key, h]));
  const rowOf = Object.fromEntries(target.skills.map((k) => [k.key, k]));
  const here = skills.map((s) => rowOf[s.key]?.score ?? null);
  // a skill measured at this star rating that has no score yet (consistency): a grey bar saying so, nothing faded
  const missing = skills.map((s, i) => here[i] === null && !!rowOf[s.key]?.needs);
  const before = skills.map((s, i) => (target.comfort || missing[i] ? null : s.score));
  const text = (i: number) => {
    const v = here[i];
    if (v === null) return "–";
    const change = rowOf[skills[i].key]?.change ?? 0;
    return target.comfort ? v.toFixed(0) : `${v.toFixed(0)} (${changeLabel(change)})`;
  };
  // the label goes after the longer of the two bars
  const label = (show: boolean) => ({ show });
  const labels = { position: "right", color: t.text, fontSize: 12, formatter: (p: unknown) => text(params(p)[0].dataIndex) };
  const longer = (i: number) => (before[i] ?? -1) > (here[i] ?? 0);
  return responsive(
    base(t, {
      grid: grid({ right: 96, bottom: 8 }),
      xAxis: valueAxis(t, {
        min: 0,
        max: 100,
        interval: 25,
        name: target.comfort
          ? `Your scores at your ${starLabel(comfort)} comfort level · 50 = expected there`
          : `Your scores at ${starLabel(target.stars)} · faded = at your ${starLabel(comfort)} comfort level`,
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
          return compareHover(s, target, comfort, helpOf[s.key]);
        },
      }),
      series: [
        {
          type: "bar",
          barMaxWidth: 22,
          barGap: "-100%",
          silent: true,
          data: before.map((v, i) => ({
            value: v ?? 0,
            itemStyle: { color: alpha(scoreColor(v), 0.3), borderRadius: [0, 3, 3, 0] },
            label: label(longer(i)),
          })),
          label: labels,
        },
        {
          type: "bar",
          barMaxWidth: 22,
          barGap: "-100%",
          data: here.map((v, i) =>
            missing[i]
              ? {
                  value: 100,
                  itemStyle: { color: alpha(C.muted, 0.18), borderRadius: [0, 3, 3, 0] },
                  label: { show: true, position: "insideLeft", color: t.muted, formatter: "Not enough data" },
                }
              : { value: v ?? 0, itemStyle: { color: scoreColor(v), borderRadius: [0, 3, 3, 0] }, label: label(!longer(i)) },
          ),
          label: labels,
          markLine: refLine(t, { xAxis: 50 }),
        },
      ],
    }),
    { ...NARROW_SKILLS(80), series: [{ label: { fontSize: 11 } }, { label: { fontSize: 11 } }] },
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

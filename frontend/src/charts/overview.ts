import type { Schemas } from "../api/client";
import { esc } from "../lib/format";
import { changeLabel, starLabel } from "../lib/starCompare";
import { base, categoryAxis, grid, niceMax, responsive, tooltip, valueAxis } from "./base";
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
export function compareHover(s: Skill, target: CompareTarget, comfort: number, help?: SkillMeta, engine = "comfort"): string {
  // what the skill measures depends on the engine (Star-Scale IRT: the notes failed against their difficulty)
  if (help && engine === "irt" && help.irt_what) help = { ...help, what: help.irt_what };
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
  if (!row || row.score === null || s.score === null) {
    // no score: what to play to get one (or, with a lower bound, to see the full score)
    const needs = s.needs ? p(`${s.at_least !== null ? "To see your full score" : "To get a score"}: ${s.needs}`) : "";
    return `<b>${esc(s.label)} at ${esc(at)}: ${esc(s.score_text)}</b>${needs}${help ? p(help.what) : ""}`;
  }
  const change = row.change ?? 0;
  let html = `<b>${esc(s.label)} at ${esc(at)}: ${row.score.toFixed(0)}${target.comfort ? "" : ` (${esc(changeLabel(change))})`}</b>`;
  if (help) html += p(help.what);
  html += p(`Points from 0 to 100: 50 = typical for a player of ${starLabel(comfort)} maps (your level), higher = stronger.`);
  const bound = row.at_least !== null; // a lower bound: everything played of the skill was held
  if (bound) html += p(`You almost never fail it on any map you played, so it is at least this${row.score < 100 ? ": harder maps could show it's higher" : ""}.`);
  if (target.comfort) html += p(`${at} is your comfort level: the score above.`);
  else if (engine === "irt" && !bound) {
    html += p(`Harder maps take points off, about 20 a star around 50 (Star-Scale IRT): ${s.score.toFixed(0)} on maps of your ${starLabel(comfort)} level, ${row.score.toFixed(0)} on ${at} maps.`);
  } else if (engine !== "irt" && row.demand !== null) {
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
export function compareBars(
  skills: Skill[],
  target: CompareTarget,
  comfort: number,
  t: ChartTheme,
  help: SkillMeta[] = [],
  engine = "comfort",
): Option {
  const helpOf = Object.fromEntries(help.map((h) => [h.key, h]));
  const rowOf = Object.fromEntries(target.skills.map((k) => [k.key, k]));
  const here = skills.map((s) => rowOf[s.key]?.score ?? null);
  // a skill measured at this star rating that has no score yet (consistency): a grey bar saying so, nothing faded
  const missing = skills.map((s, i) => here[i] === null && !!rowOf[s.key]?.needs);
  const before = skills.map((s, i) => (target.comfort || missing[i] ? null : s.score));
  // a skill the maps haven't tested to its limit shows its lower bound as a light bar: at the comfort level its own,
  // elsewhere the one the engine moved there (IRT: the hardest held, against that star rating)
  const atLeast = skills.map((s, i) =>
    here[i] !== null ? null : (rowOf[s.key]?.at_least ?? (target.comfort ? s.at_least : null)),
  );
  const text = (i: number) => {
    const v = here[i];
    // a bound at the top of the scale says nothing more than "not tested"
    if (v === null) return atLeast[i] !== null ? (atLeast[i]! >= 100 ? "not tested" : `≥ ${atLeast[i]!.toFixed(0)}`) : "–";
    const change = rowOf[skills[i].key]?.change ?? 0;
    // a lower bound (held everything played) gets "≥" — but nothing is above 100
    const bound = rowOf[skills[i].key]?.at_least != null && v < 100 ? "≥ " : "";
    return target.comfort ? `${bound}${v.toFixed(0)}` : `${bound}${v.toFixed(0)} (${changeLabel(change)})`;
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
          ? `Score, 0–100 points · 50 = typical for a player of ${starLabel(comfort)} maps (your level)`
          : `Score on ${starLabel(target.stars)} maps, 0–100 points · faded = on ${starLabel(comfort)} maps (your level)`,
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
          return compareHover(s, target, comfort, helpOf[s.key], engine);
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
              : atLeast[i] !== null
                ? {
                    value: atLeast[i],
                    itemStyle: { color: alpha(scoreColor(atLeast[i]), 0.35), borderRadius: [0, 3, 3, 0] },
                    label: { show: true, color: t.muted },
                  }
                : { value: v ?? 0, itemStyle: { color: scoreColor(v), borderRadius: [0, 3, 3, 0] }, label: label(!longer(i)) },
          ),
          label: labels,
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

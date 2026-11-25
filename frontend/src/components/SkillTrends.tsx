import { useMemo } from "react";

import { meaningful, type Trend } from "../lib/skillTrends";

/** A small chart per skill on the same timeline and scale, its latest value and the change since its first. */
export function SkillTrends({ trends, inStars }: { trends: Trend[]; inStars: boolean }) {
  const scale = useMemo(() => {
    const times = trends.flatMap((t) => t.points.map((p) => p[0]));
    const values = trends.flatMap((t) => t.points.flatMap((p) => (p[1] === null ? [] : [p[1]])));
    const lo = inStars ? Math.floor(Math.min(...values) * 2) / 2 - 0.25 : 0;
    const hi = inStars ? Math.ceil(Math.max(...values) * 2) / 2 + 0.25 : 100;
    return { t0: Math.min(...times), t1: Math.max(...times), lo, hi };
  }, [trends, inStars]);
  const x = (t: number) => (scale.t1 > scale.t0 ? ((t - scale.t0) / (scale.t1 - scale.t0)) * 100 : 50);
  const y = (v: number) => 40 - ((v - scale.lo) / (scale.hi - scale.lo || 1)) * 36 - 2;
  const show = (v: number | null) => (v === null ? "–" : inStars ? `${v.toFixed(1)}★` : v.toFixed(0));
  return (
    <ul className="skill-trends">
      {trends.map((t) => {
        // the line breaks where periods without plays lie between two points
        const segments: [number, number][][] = [[]];
        for (const [time, v] of t.points) {
          if (v === null) segments.push([]);
          else segments[segments.length - 1].push([x(time), y(v)]);
        }
        const dir = meaningful(t.change, inStars) ? (t.change! > 0 ? "up" : "down") : "flat";
        return (
          <li key={t.key} className="skill-trend">
            <div className="skill-trend__head">
              <span className="skill-trend__name">{t.label}</span>
              <span className="skill-trend__value">{show(t.last)}</span>
            </div>
            <svg className="skill-trend__line" viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true">
              {segments.filter((s) => s.length > 0).map((s, i) =>
                s.length === 1 ? (
                  <line key={i} x1={s[0][0]} y1={s[0][1]} x2={s[0][0] + 0.01} y2={s[0][1]} className="skill-trend__dot" />
                ) : (
                  <polyline key={i} points={s.map(([px, py]) => `${px},${py}`).join(" ")} />
                ),
              )}
            </svg>
            <span className={`skill-trend__change skill-trend__change--${dir}`}>
              {t.change === null ? "one period so far" : `${t.change > 0 ? "+" : t.change < 0 ? "−" : "±"}${inStars ? `${Math.abs(t.change).toFixed(1)}★` : Math.abs(t.change).toFixed(0)} since the first`}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

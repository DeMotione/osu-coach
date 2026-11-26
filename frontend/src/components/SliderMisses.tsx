import { useCallback, useMemo, useState } from "react";

import type { Schemas } from "../api/client";
import { Chart } from "../charts/Chart";
import { judgedBars } from "../charts/judged";
import type { ChartTheme } from "../charts/palette";
import { int } from "../lib/format";
import { sliderStretch } from "../lib/practise";
import {
  byLength, bySpeed, judgeSteps, type JudgedStep, lengthLabel, lengthWords, missed, speedLabel, speedWords, standing, type Step, total,
  worseStretches,
} from "../lib/sliderMisses";
import { share, times } from "../lib/verdict";
import { ChartNote } from "./ChartNote";
import { EmptyState } from "./states";
import { Card } from "./ui";
import { Verdict } from "./Verdict";

const HINT =
  "Every slider you played, by how long it is and how fast its ball moves, in circle widths. Missed = the head missed, or hit and broken later. " +
  "Each speed button shows how many you missed at that speed: press one or more to see only those speeds in the chart, All to see every speed. " +
  "The numbers are plain counts (the tiles above weigh sliders by difficulty). " +
  "Red = you miss clearly more of these than your average over all sliders, green = clearly fewer, grey = as usual, faint with a ? = too few to tell.";

/** Slider misses by length, for the ball speeds picked, with the misses per speed on the buttons (#142). */
export function SliderMissesCard({ misses }: { misses: Schemas["SliderMisses"] | null }) {
  return (
    <Card title="Slider misses by length and speed" hint={HINT}>
      {misses ? <Body m={misses} /> : <EmptyState title="Not enough sliders yet">Needs 100+ sliders.</EmptyState>}
    </Card>
  );
}

function Body({ m }: { m: Schemas["SliderMisses"] }) {
  const [picked, setPicked] = useState<number[]>([]); // none = every speed
  const all = useMemo(() => total(m, []), [m]);
  const average = all.n ? missed(all) / all.n : null;
  const speeds = useMemo(() => judgeSteps(bySpeed(m), average, speedLabel(m.speed_top)), [m, average]);
  const lengths = useMemo(() => judgeSteps(byLength(m, picked), average, lengthLabel(m.length_top)), [m, picked, average]);
  const build = useCallback(
    (t: ChartTheme) =>
      judgedBars(
        {
          groups: lengths,
          unit: "sliders",
          axisName: "slider length (circle widths)",
          describe: (l) => `sliders ${l} circle widths long`,
          count: (i) => (lengths[i].n ? `${missed(lengths[i])}/${lengths[i].n}` : ""),
          detail: (i) => `${lengths[i].head} missed at the head · ${lengths[i].broke} broken later`,
        },
        t,
      ),
    [lengths],
  );
  const toggle = (speed: number) =>
    setPicked((now) => (now.includes(speed) ? now.filter((s) => s !== speed) : [...now, speed]));
  return (
    <>
      {picked.length ? (
        <PickedVerdict step={total(m, picked)} average={average} words={speedWords(picked, m.speed_top)} picked={picked} />
      ) : (
        <AllVerdict lengths={lengths} speeds={speeds} average={average} m={m} />
      )}
      <div className="speed-picker">
        <span className="field__label" id="slider-speed-label">
          Ball speed (circle widths per second) · misses
        </span>
        <div className="speed-buttons" role="group" aria-labelledby="slider-speed-label">
          <button type="button" className="speed-button" aria-pressed={!picked.length} onClick={() => setPicked([])}
            title={`All speeds: ${int(missed(all))} of ${int(all.n)} sliders missed`}>
            All
            <span className="speed-button__misses">{int(missed(all))}</span>
          </button>
          {speeds.map((s) => (
            <button
              key={s.step}
              type="button"
              className={`speed-button speed-button--${s.standing}`}
              aria-pressed={picked.includes(s.step)}
              aria-label={`Speed ${s.label}: ${missed(s)} of ${s.n} sliders missed`}
              title={s.n ? `Speed ${s.label}: ${int(missed(s))} of ${int(s.n)} sliders missed (${share(s.rate)})` : `No sliders at speed ${s.label}`}
              disabled={!s.n}
              onClick={() => toggle(s.step)}
            >
              {s.label}
              <span className="speed-button__misses">{s.n ? int(missed(s)) : "–"}</span>
            </button>
          ))}
        </div>
      </div>
      <Chart build={build} height={320} label="Slider misses by length" />
      <ChartNote groups={lengths} unit="sliders" />
    </>
  );
}

const counted = (s: Step) => `${int(missed(s))} of ${int(s.n)} missed (${share(s.n ? missed(s) / s.n : null)})`;

/** Where in the slider they go wrong. */
function how(s: Step): string {
  if (Math.abs(s.broke - s.head) < 0.2 * missed(s)) return "Half are missed at the head, half broken later: hit the start, then stay on the ball to the end.";
  return s.broke > s.head
    ? "Most are broken after you hit the head: stay on the ball and hold the key to the end."
    : "Most are missed at the head: hit the start of the slider.";
}

/** Every speed: the lengths and the speeds that are clearly worse, the costlier of the two first. */
function AllVerdict({ lengths, speeds, average, m }: { lengths: JudgedStep[]; speeds: JudgedStep[]; average: number | null; m: Schemas["SliderMisses"] }) {
  const long = worseStretches(lengths, average)[0];
  const fast = worseStretches(speeds, average)[0];
  const excess = (s: Step) => missed(s) - s.n * (average ?? 0);
  const range = (a: number, b: number) => Array.from({ length: b - a + 1 }, (_, i) => a + i);
  const found = [
    ...(fast ? [{ s: fast, what: `at ${speedWords(range(fast.from, fast.to), m.speed_top)}`, by: "speed" as const }] : []),
    ...(long ? [{ s: long, what: lengthWords(long.from, long.to, m.length_top), by: "length" as const }] : []),
  ].sort((a, b) => excess(b.s) - excess(a.s));
  if (!found.length) return <Verdict tone="good">No length and no speed of slider stands out.</Verdict>;
  const ratio = (s: Step) => times(average ? missed(s) / s.n / average : null);
  return (
    <Verdict tone="bad" value={share(missed(found[0].s) / found[0].s.n)} practise={sliderStretch(found[0].by, found[0].s.from, found[0].s.to)}>
      Sliders <strong>{found[0].what}</strong>: {counted(found[0].s)}, {ratio(found[0].s)} your average.
      {found[1] && (
        <>
          {" "}
          Also sliders <strong>{found[1].what}</strong>: {counted(found[1].s)}.
        </>
      )}{" "}
      {how(found[0].s)}
    </Verdict>
  );
}

/** The speeds picked against your average over all sliders. */
function PickedVerdict({ step, average, words, picked }: { step: Step; average: number | null; words: string; picked: number[] }) {
  const s = standing(step, average);
  const rate = step.n ? missed(step) / step.n : null;
  const vs = average && rate !== null ? `, ${times(rate / average)} your average` : "";
  return (
    <Verdict tone={s === "worse" ? "bad" : s === "better" ? "good" : s === "few" ? "muted" : "info"} value={share(rate)} practise={s === "worse" ? sliderStretch("speed", Math.min(...picked), Math.max(...picked)) : null}>
      At <strong>{words}</strong>: {counted(step)}
      {s === "few" ? " — too few sliders to tell." : `${vs}.`} {s === "worse" && how(step)}
    </Verdict>
  );
}

import { useCallback, useMemo } from "react";

import type { Schemas } from "../api/client";
import { useSlidersReading } from "../api/queries";
import { Chart } from "../charts/Chart";
import type { ChartTheme } from "../charts/palette";
import { judgedBars } from "../charts/judged";
import { ChartNote } from "../components/ChartNote";
import { DataTable } from "../components/DataTable";
import { EmptyState, QueryView } from "../components/states";
import { Card, Page, Row, Stat, Tiles } from "../components/ui";
import { Verdict } from "../components/Verdict";
import { fmt, int, pct } from "../lib/format";
import { judge, type Judged, listed, share, times, weakest } from "../lib/verdict";

type Page_ = Schemas["SlidersReadingPage"];

const BREAK_WORDS: Record<string, [string, string]> = {
  follow: [
    "left the follow circle",
    "your cursor got off the ball: usually fast or curved sliders. Keep the cursor on the ball the whole way, don't cut corners or leave early.",
  ],
  released: ["released the key too early", "you let go before the end. Hold until the slider end — on short fast sliders too."],
  key_swap: ["switched keys", "you pressed the other key in the middle of a slider. Keep holding the same key until it ends."],
};

export default function SlidersReadingPage() {
  const q = useSlidersReading();
  return (
    <Page title="Sliders & Reading">
      <QueryView query={q}>{(d) => <Body d={d} />}</QueryView>
    </Page>
  );
}

function Body({ d }: { d: Page_ }) {
  const k = d.kpis;
  const r = d.reading;
  const ar = useMemo(() => judge(d.ar_misses.map((x) => ({ label: `AR ${x.ar}`, rate: x.miss_rate, n: x.objects }))), [d.ar_misses]);
  const byLen = useMemo(() => sliderGroups(d.by_length), [d.by_length]);
  const bySpeed = useMemo(() => sliderGroups(d.by_speed), [d.by_speed]);
  return (
    <>
      <Tiles n={4}>
        <Stat label="Sliders played" value={int(k.sliders)} />
        <Stat label="Slider head misses" value={pct(k.head_miss_rate)} />
        <Stat label="Slider breaks" value={pct(k.break_rate)} hint="Sliders hit at the head but broken later (left the follow circle or released the key)." />
        <Stat label="Missed slider ends" value={pct(k.end_miss_rate)} />
      </Tiles>
      <Row>
        <BreaksCard breaks={d.breaks} />
        <ArCard groups={ar} hits={d.hits_by_ar} />
      </Row>
      <Row>
        <SliderCard
          title="Slider misses by length"
          hint="Sliders missed at the head or broken later, by how long the slider is (circle widths)."
          axisName="slider length (circle widths)"
          describe={(l) => `sliders ${l} circle widths long`}
          rates={d.by_length}
          groups={byLen}
        />
        <SliderCard
          title="Slider misses by speed"
          hint="The same by how fast the ball moves (circle widths per second)."
          axisName="ball speed (circle widths per second)"
          describe={(l) => `sliders moving ${l} circle widths a second`}
          rates={d.by_speed}
          groups={bySpeed}
        />
      </Row>
      <Card title="Reading and consistency" hint="Miss rates in dense parts (many notes on screen) vs the rest, and whether misses cause more misses or pile up at the end of maps.">
        <Tiles n={4}>
          <Stat label="Dense parts" value={pct(r.dense_miss_rate)} hint={`Miss rate when ≥ ${fmt(r.dense_threshold, 0)} notes are on screen.`} />
          <Stat label="Sparse parts" value={pct(r.sparse_miss_rate)} />
          <Stat label="Misses after a miss" value={fmt(r.miss_after_miss_ratio, 1, "×")} hint="How much more you miss right after a miss than the difficulty explains (typical ≈ 2×)." />
          <Stat
            label="Misses in the last 20%"
            value={pct(r.end_miss_share, 0)}
            hint={`Share of misses in the last fifth of maps (${pct(r.end_object_share, 0)} of the notes).`}
          />
        </Tiles>
      </Card>
    </>
  );
}

const BAR_HINT =
  "Red = you miss clearly more of these than on average, green = clearly fewer, grey = as usual, faint with a ? = too few to tell.";

/** A slider group's share missed at the head or broken later, as a 0–1 rate. */
function sliderGroups(rates: Schemas["SliderRates"] | null): Judged[] {
  return rates ? judge(rates.rows.map((b) => ({ label: b.bin, rate: (b.head + b.broke) / 100, n: b.n }))) : [];
}

function BreaksCard({ breaks }: { breaks: Schemas["BreakShare"][] }) {
  const top = breaks[0];
  const [name] = top ? (BREAK_WORDS[top.reason] ?? [top.reason, ""]) : ["", ""];
  return (
    <Card title="Why your sliders break" hint="Sliders hit at the head but broken later (weighted by difficulty), by what went wrong.">
      {top ? (
        <>
          <Verdict tone={top.share >= 0.5 ? "bad" : "info"} value={pct(top.share, 0)} practise="sliders">
            Most of your slider breaks: you <strong>{name}</strong>.
          </Verdict>
          <ul className="list list--fill">
            {breaks.map((b) => {
              const [what, fix] = BREAK_WORDS[b.reason] ?? [b.reason, ""];
              return (
                <li key={b.reason} className="mini">
                  <span className="mini__title">
                    {pct(b.share, 0)} {what}
                  </span>
                  <span className="muted">{fix}</span>
                </li>
              );
            })}
          </ul>
        </>
      ) : (
        <Verdict tone="good">No slider breaks — nice.</Verdict>
      )}
    </Card>
  );
}

function ArCard({ groups, hits }: { groups: Judged[]; hits: Schemas["HitsByAr"][] }) {
  const build = useCallback(
    (t: ChartTheme) => judgedBars({ groups, unit: "notes", axisName: "approach rate (AR, with mods)", describe: (l) => `notes at ${l}` }, t),
    [groups],
  );
  const bad = weakest(groups);
  return (
    <Card title="By approach rate" hint={`Miss rate by AR (with mods: DT raises it). Higher AR maps are usually harder too. ${BAR_HINT}`}>
      {!groups.length ? (
        <EmptyState title="Not enough notes yet" />
      ) : (
        <>
          {bad.length ? (
            <Verdict tone="bad" value={share(bad[0].rate)} practise="reading">
              At <strong>{listed(bad.map((g) => g.label))}</strong> you miss {times(bad[0].ratio)} your average: practise reading at that
              approach rate.
            </Verdict>
          ) : (
            <Verdict tone="good">No approach rate stands out: you read low and high AR about equally well.</Verdict>
          )}
          <Chart build={build} height={240} label="Misses by approach rate" />
          <ChartNote groups={groups} />
          {hits.length > 0 && (
            <details className="more">
              <summary>300s, 100s and 50s per AR</summary>
              <DataTable
                label="Hit results per approach rate"
                rows={hits}
                rowKey={(x) => String(x.ar)}
                columns={[
                  { key: "ar", header: "AR", cell: (x) => fmt(x.ar, 1), value: (x) => x.ar, strong: true },
                  { key: "300", header: "300", cell: (x) => `${x.r300.toFixed(1)}%`, value: (x) => x.r300, align: "right" },
                  { key: "100", header: "100", cell: (x) => `${x.r100.toFixed(1)}%`, value: (x) => x.r100, align: "right" },
                  { key: "50", header: "50", cell: (x) => `${x.r50.toFixed(1)}%`, value: (x) => x.r50, align: "right" },
                  { key: "miss", header: "Miss", cell: (x) => `${x.miss.toFixed(1)}%`, value: (x) => x.miss, align: "right" },
                  { key: "plays", header: "Plays", cell: (x) => int(x.plays), value: (x) => x.plays, align: "right" },
                ]}
              />
            </details>
          )}
        </>
      )}
    </Card>
  );
}

function SliderCard({ title, hint, axisName, describe, rates, groups }: {
  title: string;
  hint: string;
  axisName: string;
  describe: (label: string) => string;
  rates: Schemas["SliderRates"] | null;
  groups: Judged[];
}) {
  const build = useCallback(
    (t: ChartTheme) => judgedBars({ groups, unit: "sliders", axisName, describe }, t),
    [groups, axisName, describe],
  );
  const bad = weakest(groups);
  const worst = bad[0] && rates?.rows.find((b) => b.bin === bad[0].label);
  const how = !worst
    ? ""
    : Math.abs(worst.broke - worst.head) < 0.2 * (worst.broke + worst.head)
      ? "missed at the head and broken later about equally: hit the start, then stay on the ball to the end"
      : worst.broke > worst.head
        ? "mostly broken after you hit the head: stay on the ball and hold the key to the end"
        : "mostly missed at the head: hit the start of the slider";
  return (
    <Card title={title} hint={`${hint} ${BAR_HINT}`}>
      {!rates ? (
        <EmptyState title="Not enough sliders yet">Needs 100+ sliders.</EmptyState>
      ) : (
        <>
          {bad.length ? (
            <Verdict tone="bad" value={share(bad[0].rate)} practise="sliders">
              <strong>{capital(describe(bad[0].label))}</strong>: {times(bad[0].ratio)} your average misses and breaks, {how}.
            </Verdict>
          ) : (
            <Verdict tone="good">No kind of slider stands out here.</Verdict>
          )}
          <Chart build={build} height={240} label={title} />
          <ChartNote groups={groups} unit="sliders" />
        </>
      )}
    </Card>
  );
}

const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

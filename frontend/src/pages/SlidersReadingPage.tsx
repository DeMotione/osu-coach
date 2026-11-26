import { useCallback, useMemo } from "react";

import type { Schemas } from "../api/client";
import { useSlidersReading } from "../api/queries";
import { Chart } from "../charts/Chart";
import type { ChartTheme } from "../charts/palette";
import { judgedBars } from "../charts/judged";
import { ChartNote } from "../components/ChartNote";
import { DataTable } from "../components/DataTable";
import { SliderMissesCard } from "../components/SliderMisses";
import { EmptyState, QueryView } from "../components/states";
import { Card, Page, Row, Stat, Tiles } from "../components/ui";
import { Verdict } from "../components/Verdict";
import { approachRates } from "../lib/practise";
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
  return (
    <>
      {/* sliders and reading at a glance: one block of tiles on top (#143) */}
      <Tiles n={8}>
        <Stat label="Sliders played" value={int(d.slider_misses ? d.slider_misses.cells.reduce((n, c) => n + c.n, 0) : k.sliders)} />
        <Stat label="Slider head misses" value={pct(k.head_miss_rate)} />
        <Stat label="Slider breaks" value={pct(k.break_rate)} hint="Sliders hit at the head but broken later (left the follow circle or released the key)." />
        <Stat label="Missed slider ends" value={pct(k.end_miss_rate)} />
        <Stat label="Misses in dense parts" value={pct(r.dense_miss_rate)} hint={`Miss rate when ≥ ${fmt(r.dense_threshold, 0)} notes are on screen.`} />
        <Stat label="Misses in sparse parts" value={pct(r.sparse_miss_rate)} hint="Miss rate when fewer notes are on screen." />
        <Stat label="Misses after a miss" value={fmt(r.miss_after_miss_ratio, 1, "×")} hint="How much more you miss right after a miss than the difficulty explains (typical ≈ 2×)." />
        <Stat
          label="Misses in the last 20%"
          value={pct(r.end_miss_share, 0)}
          hint={`Share of misses in the last fifth of maps (${pct(r.end_object_share, 0)} of the notes).`}
        />
      </Tiles>
      <Row>
        <BreaksCard breaks={d.breaks} />
        <ArCard groups={ar} hits={d.hits_by_ar} />
      </Row>
      <SliderMissesCard misses={d.slider_misses} />
    </>
  );
}

const BAR_HINT =
  "Red = you miss clearly more of these than on average, green = clearly fewer, grey = as usual, faint with a ? = too few to tell.";

function BreaksCard({ breaks }: { breaks: Schemas["BreakShare"][] }) {
  const top = breaks[0];
  const [name] = top ? (BREAK_WORDS[top.reason] ?? [top.reason, ""]) : ["", ""];
  return (
    <Card title="Why your sliders break" hint="Sliders hit at the head but broken later (weighted by difficulty), by what went wrong.">
      {top ? (
        <>
          <Verdict tone={top.share >= 0.5 ? "bad" : "info"} value={pct(top.share, 0)}>
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
            <Verdict tone="bad" value={share(bad[0].rate)} practise={approachRates(bad.map((g) => g.label))}>
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

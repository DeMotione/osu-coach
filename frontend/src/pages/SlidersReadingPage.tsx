import { useCallback } from "react";

import type { Schemas } from "../api/client";
import { useSlidersReading } from "../api/queries";
import { Chart } from "../charts/Chart";
import type { ChartTheme } from "../charts/palette";
import { arMissChart, hitsByArChart, sliderRatesChart } from "../charts/sliders";
import { DataTable } from "../components/DataTable";
import { EmptyState, QueryView } from "../components/states";
import { Alert, Card, Page, Row, Stat, Tiles } from "../components/ui";
import { fmt, int, pct } from "../lib/format";

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
  const ar = useCallback((t: ChartTheme) => arMissChart(d.ar_misses, t), [d.ar_misses]);
  const byLen = useCallback((t: ChartTheme) => (d.by_length ? sliderRatesChart(d.by_length, "slider length (circle diameters)", t) : {}), [d.by_length]);
  const bySpeed = useCallback((t: ChartTheme) => (d.by_speed ? sliderRatesChart(d.by_speed, "slider speed (circle diameters per second)", t) : {}), [d.by_speed]);
  const hits = useCallback((t: ChartTheme) => hitsByArChart(d.hits_by_ar, t), [d.hits_by_ar]);
  const worst = (s: Schemas["SliderRates"] | null) => {
    const b = s?.rows.find((x) => x.bin === s.worst);
    return b ? `Worst: ${b.bin} — ${(b.head + b.broke).toFixed(1)}% of those sliders missed or broken (${b.n} played). Red = head missed, yellow = hit but broken later.` : undefined;
  };
  return (
    <>
      <Tiles n={4}>
        <Stat label="Sliders played" value={int(k.sliders)} />
        <Stat label="Slider head misses" value={pct(k.head_miss_rate)} />
        <Stat label="Slider breaks" value={pct(k.break_rate)} hint="Sliders hit at the head but broken later (left the follow circle or released the key)." />
        <Stat label="Missed slider ends" value={pct(k.end_miss_rate)} />
      </Tiles>
      <Row>
        <Card title="Why your sliders break" sub="Sliders hit at the head but broken later (weighted by difficulty).">
          {d.breaks.length ? (
            <ul className="list list--fill">
              {d.breaks.map((b) => {
                const [name, fix] = BREAK_WORDS[b.reason] ?? [b.reason, ""];
                return (
                  <li key={b.reason} className="mini">
                    <span className="mini__title">
                      {pct(b.share, 0)} {name}
                    </span>
                    <span className="muted">{fix}</span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <Alert tone="good">No slider breaks — nice.</Alert>
          )}
        </Card>
        <Card
          title="Misses by approach rate"
          sub="Miss rate by AR (with mods; DT raises it). Higher AR maps are usually harder too — the Reading tips compare with what the difficulty predicts."
        >
          {d.ar_misses.length ? <Chart build={ar} height={260} label="Misses by approach rate" /> : <EmptyState title="Not enough notes yet" />}
        </Card>
      </Row>
      <Row>
        <Card title="Slider misses by length" sub="Head misses and breaks (after hitting the head) by slider length — find the kind of slider to practise." foot={worst(d.by_length)}>
          {d.by_length ? <Chart build={byLen} height={300} label="Slider misses by length" /> : <EmptyState title="Not enough sliders yet">Needs 100+ sliders.</EmptyState>}
        </Card>
        <Card title="Slider misses by speed" sub="The same by how fast the ball moves." foot={worst(d.by_speed)}>
          {d.by_speed ? <Chart build={bySpeed} height={300} label="Slider misses by speed" /> : <EmptyState title="Not enough sliders yet">Needs 100+ sliders.</EmptyState>}
        </Card>
      </Row>
      <Row>
        <Card title="Hits by approach rate" sub="All notes played at each AR (weighted by difficulty), split into 300 / 100 / 50 / miss. The axis starts near your lowest 300 share so the small parts are readable.">
          {d.hits_by_ar.length ? <Chart build={hits} height={300} label="Hit results by approach rate" /> : <EmptyState title="Not enough notes yet">Needs 200+ notes and 100+ per AR.</EmptyState>}
        </Card>
        <Card title="Hit results per AR" sub="The same as numbers, with how many plays each AR comes from.">
          {d.hits_by_ar.length ? (
            <DataTable
              label="Hit results per approach rate"
              rows={d.hits_by_ar}
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
          ) : (
            <EmptyState title="Not enough notes yet" />
          )}
        </Card>
      </Row>
      <Card title="Reading and consistency" sub="Miss rates in dense parts (many notes on screen) vs the rest, and whether misses cause more misses or pile up at the end of maps.">
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

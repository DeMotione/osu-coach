import { useCallback, useState } from "react";

import type { Schemas } from "../api/client";
import { useTapping } from "../api/queries";
import { Chart } from "../charts/Chart";
import type { ChartTheme } from "../charts/palette";
import { SERIES } from "../charts/palette";
import {
  fallBehindChart,
  fallBehindSpeedChart,
  keysChart,
  streamSpeedChart,
  streamsChart,
  timingChart,
  type StreamMetric,
  type TimingScale,
} from "../charts/tapping";
import { MapTable } from "../components/MapTable";
import { EmptyState, QueryView } from "../components/states";
import { Card, Field, Page, Pills, Row, Segmented, Stat, Tabs, Tiles } from "../components/ui";
import { fmt, pct, signed } from "../lib/format";

type Tapping = Schemas["TappingPage"];

export default function TappingPage() {
  const q = useTapping();
  return (
    <Page
      title="Tapping"
      sub="How you tap: timing spread and bias, how fast you can stream, whether your stamina holds in long streams, and how you use your keys."
    >
      <QueryView query={q} tiles={6}>
        {(t) => <TappingBody t={t} />}
      </QueryView>
    </Page>
  );
}

function TappingBody({ t }: { t: Tapping }) {
  const k = t.kpis;
  return (
    <>
      <Tiles n={6}>
        <Stat label="Unstable rate" value={fmt(k.ur, 0)} hint="10 × timing spread (ms), lower is better." />
        <Stat label="UR single notes" value={fmt(k.ur_single, 0)} />
        <Stat label="UR streams" value={fmt(k.ur_streams, 0)} />
        <Stat label="Average timing" value={signed(k.mean_error, 1, " ms")} hint="− = early, + = late." />
        <Stat label="300s on single notes" value={pct(k.three_hundred_rate_single, 0)} />
        <Stat label="Alternation in streams" value={pct(k.alternation_in_streams, 0)} hint="Share of stream notes hit with the other key than the previous note." />
      </Tiles>
      <Row>
        <TimingCard h={t.timing} />
        <StreamsCard s={t.streams_over_time} />
      </Row>
      <StreamSpeedCard sp={t.stream_speed} />
      <StaminaRow fb={t.fall_behind} />
      <Row>
        <KeysCard keys={t.keys} />
        <Card title="Key presses" sub="How long you hold the keys and how clean your presses are.">
          <Tiles n={4}>
            <Stat label="Typical key hold" value={fmt(t.keys.hold_ms, 0, " ms")} hint="Median of all presses, in real time." />
            <Stat label="Hold in streams" value={fmt(t.keys.press_ms_streams, 0, " ms")} />
            <Stat label="Chatter" value={fmt(t.keys.chatter_per_1000, 1)} note="per 1000 presses" hint="Double presses a few ms apart: a switch or rapid-trigger setting that bounces." />
            <Stat label="Alternation" value={pct(k.alternation_in_streams, 0)} note="in streams" />
          </Tiles>
          <p className="small muted">
            Keys: K = keyboard, M = mouse / pen buttons
            {t.keys.shares.some((s) => s.key === "L" || s.key === "R")
              ? ", L/R = lazer left / right — lazer replays only store left/right, not whether a key or a button was used."
              : "."}
          </p>
        </Card>
      </Row>
    </>
  );
}

function TimingCard({ h }: { h: Schemas["TimingHistogram"] }) {
  const [scale, setScale] = useState<TimingScale>("normal");
  const [share, setShare] = useState(15);
  const build = useCallback((th: ChartTheme) => timingChart(h, scale, share, th), [h, scale, share]);
  return (
    <Card
      title="Hit timing"
      sub="How early or late each hit was, coloured by what it scored. A narrow green peak = steady timing; the dashed line is your average — left of 0 = you tap early."
      actions={
        <Segmented
          label="Y axis"
          value={scale}
          onChange={setScale}
          options={[
            { value: "normal", label: "Normal" },
            { value: "zoom", label: "Zoom in" },
            { value: "log", label: "Log" },
          ]}
        />
      }
      foot={`${pct(h.share300, 0)} / ${pct(h.share100, 0)} / ${pct(h.share50, 1)} of hits are 300 / 100 / 50. The edges between the colours move with OD and speed mods, so they overlap a little.`}
    >
      {scale === "zoom" && (
        <Field label={`Show up to ${share}% of the highest bar`} hint="Cuts the tall 300 peak so the small bars become readable.">
          <input type="range" min={1} max={100} value={share} onChange={(e) => setShare(Number(e.target.value))} />
        </Field>
      )}
      <Chart build={build} height={330} label="Hit timing histogram" />
    </Card>
  );
}

function StreamsCard({ s }: { s: Schemas["StreamsOverTime"] | null }) {
  const [metric, setMetric] = useState<StreamMetric>("miss_rate");
  const [along, setAlong] = useState<"map" | "session">("map");
  const [keys, setKeys] = useState<string[]>(["overall"]);
  const build = useCallback((th: ChartTheme) => (s ? streamsChart(s, metric, along, keys, th) : {}), [s, metric, along, keys]);
  if (!s)
    return (
      <Card title="Streams over time" sub="When your streams start to fall apart.">
        <EmptyState title="Not enough streams yet">Streams of 7+ notes in a row: not enough of them in these replays yet.</EmptyState>
      </Card>
    );
  const options = [
    { value: "overall", label: "Overall", color: SERIES[0] },
    ...s.bands.map((b, i) => ({ value: String(b), label: `${b}–${b + s.band_width - 1}`, color: SERIES[(i % (SERIES.length - 1)) + 1] })),
  ];
  return (
    <Card
      title="Streams over time"
      sub="When your streams start to fall apart: misses and timing spread (UR) as the map or the session goes on. UR is measured with each play's own average taken out; points need 30+ notes."
    >
      <div className="controls">
        <Segmented label="Show" value={metric} onChange={setMetric} options={[{ value: "miss_rate", label: "Miss rate" }, { value: "ur", label: "UR" }]} />
        <Segmented label="Along" value={along} onChange={setAlong} options={[{ value: "map", label: "Map" }, { value: "session", label: "Session" }]} />
      </div>
      <Pills label="Stream speed (BPM)" options={options} value={keys} onChange={setKeys} />
      <Chart build={build} height={280} label="Streams over time" />
    </Card>
  );
}

function StreamSpeedCard({ sp }: { sp: Schemas["StreamSpeed"] | null }) {
  const build = useCallback((th: ChartTheme) => (sp ? streamSpeedChart(sp, th) : {}), [sp]);
  if (!sp)
    return (
      <Card title="Stream speed" sub="Misses and UR by stream speed (BPM).">
        <EmptyState title="Not enough streams yet">Streams of 7+ notes in a row: not enough of them in these replays yet.</EmptyState>
      </Card>
    );
  const weak = sp.rows.filter((r) => r.weak).map((r) => `${r.bpm}–${r.bpm + 9}`);
  return (
    <Card
      title="Stream speed"
      sub="Streams of 7+ notes by speed. Pink = misses of the fingers (no tap, too early / late), yellow = the cursor fell behind (speed-aim). Blue line: UR at that speed in the typical play; triangles = your best play; dashed = the UR expected from your other speeds."
      foot={
        <>
          Your stream speed is judged on the pink part only: clean up to ≈ {fmt(sp.comfort_bpm, 0)} BPM (green line) ·{" "}
          {sp.limit_bpm !== null ? `tapping breaks down from ≈ ${fmt(sp.limit_bpm, 0)} BPM (red line)` : "no clear breakdown speed in these replays"}.{" "}
          {weak.length ? (
            <>
              <strong>Weak spots</strong> (UR clearly above the trend, big red dots): {weak.join(", ")} BPM — practise streams at exactly those speeds.
            </>
          ) : (
            "No BPM sticks out above the trend."
          )}
        </>
      }
    >
      <Chart build={build} height={340} label="Misses and UR by stream speed" />
    </Card>
  );
}

function StaminaRow({ fb }: { fb: Schemas["FallBehind"] }) {
  const [by, setBy] = useState<"length" | "speed">("length");
  const bySpeed = by === "speed" && fb.by_speed.length >= 3;
  const build = useCallback((th: ChartTheme) => (bySpeed ? fallBehindSpeedChart(fb, th) : fallBehindChart(fb, th)), [fb, bySpeed]);
  if (!fb.available)
    return (
      <Row>
        <Card title="Stamina in long streams" sub="How precise your taps stay from the first note of a long stream to the last.">
          <EmptyState title="Not enough long streams yet">Streams of 16+ notes: not enough of them in these replays yet.</EmptyState>
        </Card>
        <Card title="Stream lengths to practise" sub="Comfortable stream length and maps to train stamina.">
          <EmptyState title="Comes with long streams">Once there are streams of 16+ notes, this shows how long you can stream and maps to practise.</EmptyState>
        </Card>
      </Row>
    );
  const hasSummary = bySpeed || !!fb.start_note || !!fb.comfort_notes || !!(fb.comfortable_maps && fb.practice_maps);
  const chart = (
    <Card
      title="Stamina in long streams"
        sub={
          bySpeed
            ? "One line per 30-BPM speed. Height = how far off your taps were, as a share of the time between two notes — so a fast stream isn't worse just because it's fast. A line that climbs = your stamina gives in at that speed."
            : "Each line is one stream length; each point = notes 1–4, 5–8, … Height = how far off your taps were on average, early or late alike. Flat = your stamina holds; climbing = your taps scatter more the longer the stream goes." +
              (fb.start_note ? " Red line: where it starts." : "")
        }
        actions={
          <Segmented
            label="Compare"
            value={by}
            onChange={setBy}
            options={[
              { value: "length", label: "By length" },
              { value: "speed", label: "By speed", disabled: fb.by_speed.length < 3 },
            ]}
          />
        }
      >
        <Chart build={build} height={340} label="Precision through long streams" />
      </Card>
  );
  if (!hasSummary) return chart;
  return (
    <Row>
      {chart}
      <StaminaSummary fb={fb} bySpeed={bySpeed} />
    </Row>
  );
}

function StaminaSummary({ fb, bySpeed }: { fb: Schemas["FallBehind"]; bySpeed: boolean }) {
  const [tab, setTab] = useState<"easy" | "push">("push");
  const at = fb.bpm ? ` at ~${fb.bpm.toFixed(0)} BPM` : "";
  const lists = fb.comfortable_maps && fb.practice_maps;
  return (
    <Card title="Stream lengths to practise" sub="Where your stamina gives in, and maps with streams of the right length.">
      {bySpeed ? (
        <>
          <ul className="list list--bullets">
            {fb.by_speed_groups.map((g) => (
              <li key={g.group}>
                <strong>{g.group}</strong>: {g.first.toFixed(0)}% → {g.last.toFixed(0)}% by note {g.notes}
              </li>
            ))}
          </ul>
          {fb.worst_speed && (
            <p>
              Your stamina gives in most at <strong>{fb.worst_speed}</strong> — practise long streams at that speed.
            </p>
          )}
        </>
      ) : fb.start_note ? (
        <p>
          <strong>Your stamina gives in after about {fb.start_note} notes</strong>
          {fb.start_seconds !== null ? ` (≈ ${fb.start_seconds.toFixed(1)} s${at})` : at}: your taps are {fmt(fb.base_ms, 0)} ms off on
          average before that and ≈ {fmt((fb.base_ms ?? 0) + (fb.growth_ms ?? 0), 0)} ms by note {fb.last_note}.
        </p>
      ) : (
        <p>
          <strong>Your precision holds</strong> through the streams measured
          {fb.comfort_notes ? ` — up to ${fb.comfort_notes} notes${at}` : at} ({fb.streams} streams of 16+ notes). No point where it
          clearly gets worse.
        </p>
      )}
      {fb.comfort_notes && fb.practice_notes && (
        <ul className="list list--bullets">
          <li>
            <strong>Comfortable:</strong> streams up to <strong>{fb.comfort_notes} notes</strong> — warm up with these.
          </li>
          <li>
            <strong>Stamina practice:</strong> streams of{" "}
            <strong>
              {fb.practice_notes[0]}–{fb.practice_notes[1]} notes
            </strong>
            , where your stamina {fb.start_note ? "starts to get in the way" : "hasn't been tested yet"}. Play them a little below your top
            speed and lengthen them step by step.
          </li>
        </ul>
      )}
      {lists && (
        <>
          <Tabs
            tabs={[
              { value: "push", label: `Stamina practice (${fb.practice_maps!.min_notes}–${fb.practice_maps!.max_notes} notes)` },
              { value: "easy", label: `Comfortable (${fb.comfortable_maps!.min_notes}–${fb.comfortable_maps!.max_notes})` },
            ]}
            value={tab}
            onChange={setTab}
          />
          <MapTable compact maps={(tab === "push" ? fb.practice_maps! : fb.comfortable_maps!).maps} maxHeight={300} />
        </>
      )}
    </Card>
  );
}

function KeysCard({ keys }: { keys: Schemas["KeyUsage"] }) {
  const build = useCallback((th: ChartTheme) => keysChart(keys.shares, th), [keys.shares]);
  return (
    <Card title="Keys used" sub="Share of your key presses per key. Even bars = you use both fingers.">
      {keys.shares.length ? <Chart build={build} height={260} label="Key usage" /> : <EmptyState title="No key presses recorded" />}
    </Card>
  );
}

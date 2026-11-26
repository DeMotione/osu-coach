import { useCallback, useState } from "react";

import type { Schemas } from "../api/client";
import { useTapping } from "../api/queries";
import { Chart } from "../charts/Chart";
import type { ChartTheme } from "../charts/palette";
import { fallBehindChart, fallBehindSpeedChart, streamSpeedChart, timingChart, type TimingScale } from "../charts/tapping";
import { MapTable } from "../components/MapTable";
import { EmptyState, QueryView } from "../components/states";
import { Card, Field, Meter, Page, Row, Segmented, Stat, Tabs, Tiles } from "../components/ui";
import { Verdict } from "../components/Verdict";
import { fmt, pct, signed } from "../lib/format";
import { bpmRanges, keysVerdict, lateInMap, timingVerdict } from "../lib/tappingWords";
import { listed, MIN_NOTES } from "../lib/verdict";

const signedMs = (v: number | null) => (v === null ? undefined : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)} ms`);

type Tapping = Schemas["TappingPage"];

export default function TappingPage() {
  const q = useTapping();
  return (
    <Page title="Tapping">
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
        <KeysCard keys={t.keys} alternation={k.alternation_in_streams} />
      </Row>
      <StreamSpeedCard sp={t.stream_speed} />
      <StaminaRow fb={t.fall_behind} late={lateInMap(t.streams_over_time)} />
    </>
  );
}

function TimingCard({ h }: { h: Schemas["TimingHistogram"] }) {
  const [scale, setScale] = useState<TimingScale>("normal");
  const [share, setShare] = useState(15);
  const build = useCallback((th: ChartTheme) => timingChart(h, scale, share, th), [h, scale, share]);
  const said = timingVerdict(h.mean);
  return (
    <Card
      title="Hit timing"
      hint="How early or late each hit was, coloured by what it scored. A narrow green peak = steady timing; the dashed line is your average — left of 0 = you tap early."
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
      {said && (
        <Verdict tone={said.tone} value={signedMs(h.mean)} practise={said.tone === "bad" ? "accuracy" : null}>
          {said.text}
        </Verdict>
      )}
      {scale === "zoom" && (
        <Field label={`Show up to ${share}% of the highest bar`} hint="Cuts the tall 300 peak so the small bars become readable.">
          <input type="range" min={1} max={100} value={share} onChange={(e) => setShare(Number(e.target.value))} />
        </Field>
      )}
      <Chart build={build} height={330} label="Hit timing histogram" />
    </Card>
  );
}

function StreamSpeedCard({ sp }: { sp: Schemas["StreamSpeed"] | null }) {
  const build = useCallback((th: ChartTheme) => (sp ? streamSpeedChart(sp, th) : {}), [sp]);
  if (!sp)
    return (
      <Card title="Stream speed" hint="How steady your timing is at each stream speed (BPM).">
        <EmptyState title="Not enough streams yet">Streams of 7+ notes in a row: not enough of them in these replays yet.</EmptyState>
      </Card>
    );
  const weak = sp.rows.filter((r) => r.weak && r.objects >= MIN_NOTES).map((r) => r.bpm);
  const clean = sp.comfort_bpm !== null ? `clean up to ≈ ${fmt(sp.comfort_bpm, 0)} BPM` : null;
  return (
    <Card
      title="Stream speed"
      hint="Streams of 7+ notes by speed. Bars: how much your timing spreads (UR) at that speed in a typical play — lower is steadier. Red = a weak spot: clearly more than your other speeds lead to expect (dashed line). Faint with a ? = too few notes to tell. Point at a bar for its misses and your best play."
    >
      {weak.length ? (
        <Verdict tone="bad" value={`${bpmRanges(weak)[0]}`} practise="speed">
          Your streams wobble at <strong>{listed(bpmRanges(weak))} BPM</strong>: your timing spreads clearly more there than at your
          other speeds. Practise streams at exactly those speeds.{clean ? ` Otherwise ${clean}.` : ""}
        </Verdict>
      ) : (
        <Verdict tone="good" value={sp.comfort_bpm !== null ? `${fmt(sp.comfort_bpm, 0)}` : undefined}>
          {clean ? `Your streams are ${clean}` : "Your streams are steady"}, with no speed that sticks out.
          {sp.limit_bpm !== null ? ` Tapping breaks down from ≈ ${fmt(sp.limit_bpm, 0)} BPM.` : ""}
        </Verdict>
      )}
      <Chart build={build} height={300} label="Timing spread by stream speed" />
      <p className="chart-note">
        <span className="chart-note__item">
          <span className="chart-note__key chart-note__key--line" /> UR expected from your other speeds
        </span>
        <span className="chart-note__item">
          <span className="chart-note__key chart-note__key--bad" /> weak spot
        </span>
        <span className="chart-note__item">? = too few notes to tell</span>
      </p>
    </Card>
  );
}

function StaminaRow({ fb, late }: { fb: Schemas["FallBehind"]; late: string | null }) {
  const [by, setBy] = useState<"length" | "speed">("length");
  const bySpeed = by === "speed" && fb.by_speed.length >= 3;
  const build = useCallback((th: ChartTheme) => (bySpeed ? fallBehindSpeedChart(fb, th) : fallBehindChart(fb, th)), [fb, bySpeed]);
  if (!fb.available)
    return (
      <>
        <Card title="Stamina in long streams" hint="How precise your taps stay from the first note of a long stream to the last.">
          <EmptyState title="Not enough long streams yet">Streams of 16+ notes: not enough of them in these replays yet.</EmptyState>
        </Card>
        <Card title="Stream lengths to practise" hint="Comfortable stream length and maps to train stamina.">
          <EmptyState title="Comes with long streams">Once there are streams of 16+ notes, this shows how long you can stream and maps to practise.</EmptyState>
        </Card>
      </>
    );
  const hasSummary = bySpeed || !!fb.start_note || !!fb.comfort_notes || !!(fb.comfortable_maps && fb.practice_maps);
  const chart = (
    <Card
      className="stamina-chart-card"
      title="Stamina in long streams"
        hint={
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
        <StaminaVerdict fb={fb} late={late} />
        <Chart build={build} height={300} label="Precision through long streams" />
      </Card>
  );
  if (!hasSummary) return chart;
  return (
    <>
      {chart}
      <StaminaSummary fb={fb} bySpeed={bySpeed} />
    </>
  );
}

function StaminaVerdict({ fb, late }: { fb: Schemas["FallBehind"]; late: string | null }) {
  const at = fb.bpm ? ` at ~${fb.bpm.toFixed(0)} BPM` : "";
  if (fb.start_note)
    return (
      <Verdict tone="bad" value={`${fb.start_note} notes`} practise="stamina">
        Your stamina gives in after about <strong>{fb.start_note} notes</strong>
        {fb.start_seconds !== null ? ` (≈ ${fb.start_seconds.toFixed(1)} s${at})` : at}: your taps drift from {fmt(fb.base_ms, 0)} ms off
        to ≈ {fmt((fb.base_ms ?? 0) + (fb.growth_ms ?? 0), 0)} ms by note {fb.last_note}. {late}
      </Verdict>
    );
  return (
    <Verdict tone={late ? "bad" : "good"} value={fb.comfort_notes ? `${fb.comfort_notes} notes` : undefined} practise={late ? "stamina" : null}>
      Your precision holds through long streams{fb.comfort_notes ? ` up to ${fb.comfort_notes} notes${at}` : at}. {late}
    </Verdict>
  );
}

function StaminaSummary({ fb, bySpeed }: { fb: Schemas["FallBehind"]; bySpeed: boolean }) {
  const [tab, setTab] = useState<"easy" | "push">("push");
  const lists = fb.comfortable_maps && fb.practice_maps;
  return (
    <Card title="Stream lengths to practise" hint="Where your stamina gives in, and maps with streams of the right length.">
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
      ) : null}
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
          <MapTable key={tab} compact maps={(tab === "push" ? fb.practice_maps! : fb.comfortable_maps!).maps} maxHeight={300} />
          <p className="small muted">Lists keep the stated stream-length range and exclude maps in your replay dataset.</p>
          {!(tab === "push" ? fb.practice_maps! : fb.comfortable_maps!).maps.length && <p className="small muted">
            {Object.entries((tab === "push" ? fb.practice_maps! : fb.comfortable_maps!).excluded ?? {}).map(([reason, count]) => `${reason}: ${count}`).join(" · ")}
          </p>}
        </>
      )}
    </Card>
  );
}

function KeysCard({ keys, alternation }: { keys: Schemas["KeyUsage"]; alternation: number | null }) {
  const said = keysVerdict(keys, alternation);
  const shares = [...keys.shares].sort((a, b) => b.share - a.share);
  return (
    <Card title="Keys" hint="Which keys you press and how cleanly: even shares between your two main keys = you use both fingers. K = keyboard, M = mouse / pen buttons, L / R = lazer's left / right (lazer replays don't say whether a key or a button was used).">
      {said ? (
        <Verdict tone={said.tone}>{said.text}</Verdict>
      ) : (
        <EmptyState title="No key presses recorded" />
      )}
      {shares.length > 0 && (
        <ul className="list key-shares" aria-label="Share of presses per key">
          {shares.map((s) => (
            <li key={s.key}>
              <span className="key-shares__key">{s.key}</span>
              <Meter value={s.share * 100} color="var(--accent)" />
              <span className="num">{Math.round(s.share * 100)}%</span>
            </li>
          ))}
        </ul>
      )}
      <Tiles n={3}>
        <Stat label="Typical key hold" value={fmt(keys.hold_ms, 0, " ms")} hint="Median of all presses, in real time." />
        <Stat label="Hold in streams" value={fmt(keys.press_ms_streams, 0, " ms")} />
        <Stat label="Chatter" value={fmt(keys.chatter_per_1000, 1)} note="per 1000 presses" hint="Double presses a few ms apart: a switch or rapid-trigger setting that bounces." />
      </Tiles>
    </Card>
  );
}

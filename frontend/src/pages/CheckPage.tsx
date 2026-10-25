import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import type { Schemas } from "../api/client";
import { uploadFiles, useCheckReplays, useCheckReport } from "../api/queries";
import { playTimingChart, rangeStats } from "../charts/check";
import { Chart } from "../charts/Chart";
import type { ChartTheme } from "../charts/palette";
import type { echarts } from "../charts/echarts";
import { ClicksView } from "../components/Clicks";
import { DataTable } from "../components/DataTable";
import { IconArrowLeft, IconExternal, IconMagnify, IconPlay } from "../components/icons";
import { EmptyState, ErrorCard } from "../components/states";
import { Alert, Card, Dropzone, Field, Page, Row, Stat, Switch, Tiles } from "../components/ui";
import { clock, fmt, int, localTime, pct, signed, stars } from "../lib/format";
import { Md } from "../lib/markdown";

type Report = Schemas["CheckReport"];

export default function CheckPage() {
  const [params, setParams] = useSearchParams();
  const opened = params.get("path");
  const [onlyMap, setOnlyMap] = useState<boolean>(!!opened);
  const [chosen, setChosen] = useState<string | null>(null);
  const [online, setOnline] = useState(true);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const list = useCheckReplays(opened, onlyMap);
  const replays = list.data?.replays ?? [];
  const path = chosen && replays.some((r) => r.path === chosen) ? chosen : list.data?.selected ?? null;
  const current = replays.find((r) => r.path === path);
  const report = useCheckReport(current?.analysable ? path : null, online);

  const open = (p: string, focus = true) => {
    setChosen(null);
    setOnlyMap(focus);
    setParams({ path: p });
  };
  // the replay opened can't be read (moved, deleted, not a replay): back to the list of your replays (#17)
  const back = () => {
    setChosen(null);
    setOnlyMap(false);
    setParams({});
  };

  return (
    <Page title="Detailed Map Analysis">
      <Row>
        <Card title="Pick a replay" hint="Newest first. Pick a row on the Replays page and press Detailed map analysis to open it here.">
          <Dropzone
            accept=".osr"
            multiple={false}
            title="Check a replay file"
            help="Any .osr — e.g. exported from lazer's results screen, or someone else's replay."
            onFiles={async (files) => {
              setUploadError(null);
              try {
                const [up] = await uploadFiles(files);
                if (up) open(up.path);
              } catch (e) {
                setUploadError((e as Error).message);
              }
            }}
          />
          {uploadError && <Alert tone="bad">{uploadError}</Alert>}
          {list.data && !list.data.available ? (
            <Alert tone="info">No osu! installation was found automatically. Drop a replay file above, or scan a folder on the Replays page.</Alert>
          ) : list.error ? (
            <>
              <Alert tone="bad">{list.error.message}</Alert>
              {opened && (
                <button type="button" className="btn btn--block" onClick={back}>
                  <IconArrowLeft /> Back to your replays
                </button>
              )}
            </>
          ) : (
            <>
              <Field label="Replay">
                <select className="select" value={path ?? ""} onChange={(e) => setChosen(e.target.value)} disabled={!replays.length}>
                  {replays.map((r) => (
                    <option key={r.path} value={r.path}>
                      {localTime(r.played_at)} · {r.player || "(no name)"} · {r.map} · {r.mods}
                      {r.accuracy !== null ? ` · ${pct(r.accuracy, 2)}` : ""}
                    </option>
                  ))}
                </select>
              </Field>
              <div className="controls">
                <Switch
                  label="Only plays of this map"
                  checked={onlyMap}
                  disabled={!list.data?.focus_md5}
                  hint="List only your replays of the map shown (all of them, not just the newest)."
                  onChange={(v) => {
                    setOnlyMap(v);
                    if (v && path && path !== opened) open(path, true);
                  }}
                />
                <Switch label="Download the map if it's missing" checked={online} onChange={setOnline} />
              </div>
              {list.data && !replays.length && <Alert tone="info">No osu!standard replays found. Drop a replay file above, or scan on the Replays page.</Alert>}
            </>
          )}
        </Card>
        <SummaryCard report={report.data} pending={report.isFetching && !report.data} current={current} />
      </Row>
      {current && !current.analysable ? (
        <Alert tone="warn">This replay can't be checked: {current.reason}.</Alert>
      ) : report.error ? (
        <ErrorCard error={report.error} onRetry={() => void report.refetch()} />
      ) : report.data ? (
        <ReportBody r={report.data} onOpen={(p) => open(p, true)} />
      ) : report.isFetching ? (
        <div className="skeleton" style={{ height: 420 }} />
      ) : null}
    </Page>
  );
}

function SummaryCard({ report, pending, current }: { report?: Report; pending: boolean; current?: Schemas["CheckReplay"] }) {
  if (!report)
    return (
      <Card title="The play" hint="Result, settings and what cost the play.">
        {pending ? (
          <EmptyState icon={<span className="spinner" />} title="Checking the replay…">
            Every note is replayed against the beatmap; your other plays of the map are read for the comparison.
          </EmptyState>
        ) : (
          <EmptyState icon={<IconMagnify />} title={current ? "Pick a replay that can be checked" : "No replay picked"} />
        )}
      </Card>
    );
  const s = report.summary;
  return (
    <Card
      title={s.map}
      hint={
        <>
          {s.player || "(no name)"} · played {localTime(s.played_at)} · osu!{s.client} · {s.mods_label} · mapped by {s.creator ?? "?"} ·{" "}
          {clock(s.length_s)}
          {s.beatmap_id && (
            <>
              {" "}
              ·{" "}
              <a href={`https://osu.ppy.sh/b/${s.beatmap_id}`} target="_blank" rel="noreferrer noopener">
                beatmap page <IconExternal width={12} height={12} />
              </a>
            </>
          )}
        </>
      }
    >
      <ul className="list list--bullets">
        {s.verdict.map((v) => (
          <li key={v}>
            <Md>{v}</Md>
          </li>
        ))}
      </ul>
      {!s.sim_exact && (
        <p className="small muted">
          The re-simulation differs a little from the result stored in the replay ({pct(s.sim_agreement ?? 0)} agreement), so times may be
          slightly off.
        </p>
      )}
    </Card>
  );
}

function ReportBody({ r, onOpen }: { r: Report; onOpen: (path: string) => void }) {
  const s = r.summary;
  return (
    <>
      <Tiles n={6}>
        <Stat label="Accuracy" value={pct(s.accuracy, 2)} />
        <Stat label="Combo" value={s.map_combo ? `${int(s.combo)}/${int(s.map_combo)}` : int(s.combo)} />
        <Stat label="Misses" value={int(s.misses)} hint="Judged misses, as on the results screen." />
        <Stat label="Slider breaks" value={int(s.slider_breaks)} />
        <Stat label="UR" value={fmt(s.ur, 0)} hint="Unstable rate of this play: 10 × the spread of your hit timing (ms)." />
        <Stat label="Difficulty" value={stars(s.stars)} hint={`Star rating with ${s.mods_label}.`} />
      </Tiles>
      <Tiles n={6}>
        <Stat label="BPM" value={fmt(s.bpm, 0)} hint="Main BPM of the map at the speed of this play." />
        <Stat label="Speed" value={`×${+s.rate.toFixed(3)}`} hint="1.5 = DT/NC, 0.75 = HT; lazer can set any rate." />
        <Stat label="AR" value={fmt(s.ar, 1)} hint="With the mods of this play (HR, EZ, DT, Difficulty Adjust, …)." />
        <Stat label="OD" value={fmt(s.od, 1)} />
        <Stat label="CS" value={fmt(s.cs, 1)} />
        <Stat label="HP" value={fmt(s.hp, 1)} />
      </Tiles>
      <Card
        title="Misses and combo breaks"
        hint="One row per miss or combo break, in map order. Time = where it is in the map (type it into the osu! editor to jump there); Reason = why it was missed."
      >
        {r.events.length ? (
          <DataTable
            label="Misses and combo breaks"
            rows={r.events}
            rowKey={(e, i) => `${e.time}-${i}`}
            maxHeight={380}
            columns={[
              { key: "t", header: "Time", cell: (e) => <code>{e.timestamp}</code>, value: (e) => e.time, title: "Map time as the osu! editor shows it (mm:ss:mmm)." },
              { key: "what", header: "What", cell: (e) => e.what },
              { key: "why", header: "Reason", cell: (e) => e.reason_label },
              { key: "detail", header: "Detail", cell: (e) => e.detail, wrap: true },
              { key: "pattern", header: "Pattern", cell: (e) => e.pattern || "–" },
            ]}
          />
        ) : (
          <Alert tone="good">No misses and no combo breaks in this play.</Alert>
        )}
      </Card>
      {r.sections.length > 0 && (
        <Card
          title="Where they cluster — parts to practise"
          hint="Each part starts a measure before the first miss and ends just after the last one, on the notes of the map, so you can cut it out exactly."
          foot="How to practise a part: open the map in the editor and use File → Create a new difficulty (stable copies the current notes into it — delete everything outside the two times; lazer: copy the notes between the times first, then paste them into the new difficulty). Play the part with the same mods and speed until it is clean, then play the whole map again and open the new replay here: the table of your plays shows whether it helped."
        >
          <ul className="list">
            {r.sections.map((x) => (
              <li key={x.start} className="mini">
                <span className="mini__title">
                  <code>{x.start}</code> – <code>{x.end}</code> · {x.seconds.toFixed(1)} s, {x.notes} notes
                </span>
                <span className="muted">
                  {x.count}: {x.reasons.map((q) => `${q.count} ${q.label}`).join(", ")}
                  {x.pattern ? ` · ${x.pattern}` : ""} (misses {x.first_event}–{x.last_event})
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {r.timing && <TimingCard tm={r.timing} />}
      <MapPlaysCard plays={r.map_plays} onOpen={onOpen} />
      {r.clicks_screen && r.clicks_movement && (
        <Row>
          <Card title="Where your clicks land — on screen" hint="Every hit and aim miss of this play, in circle radii from the note's centre.">
            <ClicksView clicks={r.clicks_screen} />
          </Card>
          <Card title="Where your clicks land — along the jump" hint="The jumps of this play, turned so every jump goes right: over- and undershoot.">
            <ClicksView clicks={r.clicks_movement} />
          </Card>
        </Row>
      )}
    </>
  );
}

function TimingCard({ tm }: { tm: Schemas["PlayTiming"] }) {
  const end = Math.ceil(tm.length_ms / 1000) * 1000;
  const [range, setRange] = useState<[number, number]>([0, end]);
  const build = useCallback((t: ChartTheme) => playTimingChart(tm, t), [tm]);
  const events = useMemo(
    () => ({
      datazoom: (_: unknown, chart: echarts.ECharts) => {
        const dz = (chart.getOption() as { dataZoom?: { startValue?: number; endValue?: number }[] }).dataZoom?.[0];
        if (dz && dz.startValue !== undefined && dz.endValue !== undefined) setRange([dz.startValue, dz.endValue]);
      },
    }),
    [],
  );
  const st = rangeStats(tm, range[0], range[1]);
  const zoomed = range[0] > 0 || range[1] < end;
  return (
    <Card
      title="Timing through the map"
      hint="Map time along the bottom. Each dot is one hit; the pink line is your running average (above 0 = late). Dotted lines: the 300 window. Red ×: misses, triangles: combo breaks without a miss. Drag the handles below the chart (or scroll on it) to zoom into a section."
    >
      <Tiles n={4}>
        <Stat label={zoomed ? "Hits in range" : "Hits"} value={int(st.n)} note={zoomed ? `${clockMs(range[0])} – ${clockMs(range[1])}` : "whole map"} />
        <Stat label="Average error" value={signed(st.mean, 1, " ms")} />
        <Stat label="Unstable rate" value={fmt(st.ur, 0)} />
        <Stat label="Misses / breaks" value={int(st.marks)} />
      </Tiles>
      <Chart build={build} height={380} label="Hit timing through the map" events={events} />
    </Card>
  );
}

const clockMs = (ms: number) => clock(ms / 1000);

function MapPlaysCard({ plays, onOpen }: { plays: Schemas["MapPlays"]; onOpen: (path: string) => void }) {
  const [sel, setSel] = useState<Schemas["MapPlay"] | null>(null);
  const line = plays.first
    ? "First play of this map in your saved history."
    : plays.same_settings_plays
      ? `Same settings (${plays.settings}): ${plays.same_settings_plays} other play(s); best ${plays.best_misses} misses (${pct(plays.best_accuracy, 2)}) — this is ${plays.is_best ? "your best play with these settings" : "not your best with these settings"}.` +
        (plays.ur_median !== null ? ` UR ${fmt(plays.rows.find((r) => r.this)?.ur ?? null, 0)} vs ${fmt(plays.ur_median, 0)} usually.` : "")
      : `First play with these settings (${plays.settings}).`;
  return (
    <Card
      title="All your plays of this map"
      hint="Every play of this map in your history and on this computer, newest first. Only plays with the same speed and settings (DT/HT/custom rate, AR/OD/CS/HP, HD/FL) are compared."
      actions={
        <button
          type="button"
          className="btn btn--primary btn--sm"
          disabled={!sel || sel.this || !sel.path_exists}
          title={sel && !sel.path_exists ? "The replay file of that play is no longer on this computer (only its numbers were saved)." : undefined}
          onClick={() => sel && onOpen(sel.path)}
        >
          <IconPlay /> Open this play
        </button>
      }
      foot={plays.other_settings ? `${plays.other_settings} play(s) with other settings are listed but not compared.` : undefined}
    >
      <p>{line}</p>
      {plays.rows.length > 1 && (
        <DataTable
          label="Plays of this map"
          rows={plays.rows}
          rowKey={(p, i) => `${p.path}-${p.played_at}-${i}`}
          selected={sel ? `${sel.path}-${sel.played_at}-${plays.rows.indexOf(sel)}` : null}
          onSelect={(p) => setSel(p)}
          maxHeight={360}
          columns={[
            { key: "tag", header: "", cell: (p) => (p.this ? <span className="badge badge--info">this play</span> : p.same_settings ? <span className="badge badge--muted">same settings</span> : "") },
            { key: "played", header: "Played", cell: (p) => localTime(p.played_at), value: (p) => p.played_at },
            { key: "mods", header: "Mods", cell: (p) => p.mods_label },
            { key: "settings", header: "Settings", cell: (p) => p.settings_label },
            { key: "bpm", header: "BPM", cell: (p) => fmt(p.bpm, 0), value: (p) => p.bpm, align: "right" },
            { key: "stars", header: "Difficulty", cell: (p) => fmt(p.stars, 2, " ★"), value: (p) => p.stars, align: "right" },
            { key: "acc", header: "Accuracy", cell: (p) => pct(p.accuracy, 2), value: (p) => p.accuracy, align: "right" },
            { key: "miss", header: "Misses", cell: (p) => int(p.misses), value: (p) => p.misses, align: "right" },
            { key: "combo", header: "Combo", cell: (p) => int(p.combo), value: (p) => p.combo, align: "right" },
            { key: "ur", header: "UR", cell: (p) => fmt(p.ur, 0), value: (p) => p.ur, align: "right" },
            { key: "passed", header: "Passed", cell: (p) => (p.passed === null ? "–" : p.passed ? "yes" : "no") },
          ]}
        />
      )}
    </Card>
  );
}

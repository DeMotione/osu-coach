import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";

import type { Schemas } from "../api/client";
import { useAim, useAnalysedReplays, useClicks } from "../api/queries";
import { directionsChart, distanceChart } from "../charts/aim";
import { Chart } from "../charts/Chart";
import type { ChartTheme } from "../charts/palette";
import { ClicksView } from "../components/Clicks";
import { DataTable } from "../components/DataTable";
import { DateRangePicker } from "../components/DateRangePicker";
import { PlayfieldGrid, QuadrantGrid } from "../components/Heat";
import { RangeSlider } from "../components/RangeSlider";
import { EmptyState, QueryView } from "../components/states";
import { Alert, Card, Page, Row, Segmented, Stat, Tiles } from "../components/ui";
import { clickFilter, clicksCaption, starBounds } from "../lib/clicks";
import { dayOf, type DayRange } from "../lib/dateRange";
import { fmt, int, pct, signed } from "../lib/format";

export default function AimPage() {
  const q = useAim();
  return (
    <Page title="Aim">
      <QueryView query={q}>{(aim) => <AimBody aim={aim} />}</QueryView>
    </Page>
  );
}

function AimBody({ aim }: { aim: Schemas["AimPage"] }) {
  const k = aim.kpis;
  const wq = aim.worst_quadrant;
  const dirs = useCallback((t: ChartTheme) => directionsChart(aim.directions, t), [aim.directions]);
  const dist = useCallback((t: ChartTheme) => distanceChart(aim.distances, t), [aim.distances]);
  return (
    <>
      <Tiles n={3}>
        <Stat label="Jump miss rate" value={pct(k.jump_miss_rate)} />
        <Stat label="Near misses" value={pct(k.near_miss_share, 0)} hint="Aim misses that landed within 1.4 radii — just outside the circle." />
        <Stat label="Jump distance error" value={signed(k.jump_along_pct, 1, "%")} hint="Median over/undershoot along the jump direction, as % of the jump length." />
      </Tiles>
      {wq &&
        (wq.significant ? (
          <Alert tone="warn">
            Weakest quadrant: <strong>{wq.quadrant}</strong> — {pct(wq.miss_rate)} misses vs {pct(wq.rest_miss_rate)} elsewhere (
            {fmt(wq.relative_risk, 1)}×). See <Link to="/tips">Tips</Link> for how to fix it.
          </Alert>
        ) : (
          <Alert tone="info">
            Weakest quadrant: <strong>{wq.quadrant}</strong> — {pct(wq.miss_rate)} misses vs {pct(wq.rest_miss_rate)} elsewhere (
            {fmt(wq.relative_risk, 1)}×). The difference is still within noise.
          </Alert>
        ))}
      <Row>
        <Card title="Miss rate by screen quadrant" hint="The playfield cut into four. Each cell: share of the notes there you missed, and misses / notes. Pinker = more misses.">
          <QuadrantGrid cells={aim.quadrants} />
        </Card>
        <Card title="Where on the playfield you miss" hint="A finer grid of the playfield as you see it: the pinker a cell, the more of its notes you missed. Empty cells: too few notes there.">
          <PlayfieldGrid grid={aim.grid} />
        </Card>
      </Row>
      <Row>
        <ClicksCard />
        <Card
          title="Miss rate by jump direction"
          hint="Each wedge is a direction the cursor moves in to reach the note (jumps of 1+ circle). The longer the wedge, the more of those jumps you missed."
        >
          <Chart build={dirs} height={420} label="Miss rate by jump direction" />
        </Card>
      </Row>
      <Row>
        <Card
          title="By jump distance"
          hint="Bars: miss rate by how far the note is from the previous one (circle diameters). Line: how far past (+) or short of (−) the note you click, in circle radii."
        >
          <Chart build={dist} height={340} label="Miss rate and over/undershoot by jump distance" />
        </Card>
        <AnglesCard angles={aim.angles} />
      </Row>
    </>
  );
}

const CLICKS_HINT = "The click that hit each note and the closest click of each aim miss, in circle radii from the note's centre.";

function ClicksCard() {
  const [view, setView] = useState<"screen" | "movement">("screen");
  const replays = useAnalysedReplays();
  const plays = useMemo(() => replays.data ?? [], [replays.data]);
  const bounds = useMemo(() => starBounds(plays), [plays]);
  const played = useMemo(() => new Set(plays.flatMap((r) => (r.played_at ? [dayOf(r.played_at)] : []))), [plays]);
  const [stars, setStars] = useState<[number, number] | null>(null);
  const [dates, setDates] = useState<DayRange | null>(null);
  // the chart follows the slider once it stops moving
  const [chosen, setChosen] = useState(stars);
  useEffect(() => {
    const t = setTimeout(() => setChosen(stars), 300);
    return () => clearTimeout(t);
  }, [stars]);
  const filter = useMemo(() => clickFilter(chosen, bounds, dates), [chosen, bounds, dates]);
  const q = useClicks(view, filter);
  const [low, high] = stars ?? bounds ?? [0, 0];
  const caption = q.data?.enough ? clicksCaption(q.data) : "";
  return (
    <Card
      className="clicks-card"
      title="Where your clicks land"
      hint={caption ? `${CLICKS_HINT}\n\n${caption}` : CLICKS_HINT}
      actions={
        <Segmented
          label="View"
          value={view}
          onChange={setView}
          options={[
            { value: "screen", label: "On screen" },
            { value: "movement", label: "Along the jump" },
          ]}
        />
      }
    >
      {/* two equal columns, each a label and its value over a control, one column on narrow cards */}
      <div className="clicks-filters">
        {bounds && bounds[1] > bounds[0] && (
          <RangeSlider label="Star rating" min={bounds[0]} max={bounds[1]} step={0.1} value={[low, high]}
            onChange={setStars} format={(v) => `${v.toFixed(1)}★`} />
        )}
        <div className="labelled">
          <div className="labelled__head">
            <span className="field__label">Played</span>
            {q.data && plays.length > 0 && (
              <span className="labelled__value">
                {int(q.data.plays)} of {int(plays.length)} plays
              </span>
            )}
          </div>
          <DateRangePicker value={dates} onChange={setDates} played={played} label="Played" />
        </div>
      </div>
      {q.data ? (
        <ClicksView clicks={q.data} empty={Object.keys(filter).length ? "Not enough clicks in these plays" : undefined} />
      ) : (
        <div className="skeleton grow" style={{ minHeight: 360 }} />
      )}
    </Card>
  );
}

function AnglesCard({ angles }: { angles: Schemas["AngleRow"][] }) {
  return (
    <Card
      title="By angle between jumps"
      hint="Sharp = back-and-forth jumps, wide = jumps that keep going in one direction. Notes are weighted by difficulty."
    >
      {angles.length ? (
        <DataTable
          label="Miss rate by angle between jumps"
          rows={angles}
          rowKey={(r) => r.bin}
          columns={[
            { key: "bin", header: "Angle between jumps", cell: (r) => r.bin },
            { key: "n", header: "Notes", cell: (r) => int(r.objects), value: (r) => r.objects, align: "right" },
            { key: "rate", header: "Miss rate", cell: (r) => pct(r.miss_rate), value: (r) => r.miss_rate, align: "right" },
          ]}
        />
      ) : (
        <EmptyState title="Not enough jumps yet" />
      )}
    </Card>
  );
}
